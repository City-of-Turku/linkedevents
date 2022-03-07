# -*- coding: utf-8 -*-

# Dependencies.
import requests
import asyncio
import aiohttp
import logging
import math
import time
import json
import copy
import sys

# requires langdetect package.
from langdetect import detect, detect_langs

# Django:
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import DataSource, BaseModel, Place
from .base import Importer, register_importer
from django.utils.html import strip_tags
from django.conf import settings

# GeoDjango:
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.gdal import SpatialReference, CoordTransform
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.contrib.gis import gdal
from django.db import connection, reset_queries

# Type checking:
from typing import TYPE_CHECKING, Any, Tuple, List


# Per module logger
logger = logging.getLogger(__name__)

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0',
}

async def fetch(session, url, id) -> dict:
    async with session.get(url) as response:
        data = await response.read()
        json_response = json.loads(data)
        result = json_response.get('results', None)
        if result:
            return result
        else:
            err_result = json_response.get('detail', None)
            if err_result:
                raise Exception(
                    "Palvelukartta unit reported: '%s' for page: %s" % (err_result, id))
            # If the API ever changes error handling in the future, notify about it.
            raise Exception(
                "Palvelukartta unit: '%s' request did not fail, but API parsing was incorrect. API has changed?" % id)


async def main(unit_pages) -> dict:
    async with aiohttp.ClientSession() as session:

        tasks = []
        for page_no in range(1, unit_pages+1):
            # Testipalvelukartta needs turku VPN connection.
            URL = "https://testipalvelukartta.turku.fi/api/v2/unit/?page=%s&page_size=50" % page_no
            tasks.append(fetch(session, URL, page_no))
        try:
            res = await asyncio.gather(*tasks, return_exceptions=False)
            return res
        except Exception as e:
            logger.warn(e)
            await asyncio.sleep(1)


def async_main(retry_count=3) -> dict:
    '''
    Currently works in 3.6 Python
    Works for both 3.6 and 3.7 Python versions.
    
    Fetch page_count by calculating page_size 'count'
    by dividing it with default value 20 (servicemap).
    Testipalvelukartta needs turku VPN connection.
    '''
    url = "https://testipalvelukartta.turku.fi/api/v2/unit"

    try:
        fetch = requests.get(url, headers=headers)
        response = fetch.json()
        count = response["count"]
        calc = math.modf(count/50)

        if calc[0] != float(0):
            page_count = int(calc[1]+1)
            print(page_count)
        else:
            page_count = int(calc[1])
            print(page_count)
    except Exception as e:
         raise Exception(
            "Something went wrong in the 'page count' pre-processing phase of TPRAPI: %s" % e)

    for connection_retries in range(retry_count):
        if sys.version_info >= (3, 8, 0):
            res = asyncio.run(main(unit_pages=page_count))
            if res:
                return res
        else:
            # 3.6+ support.
            loop = asyncio.get_event_loop()
            task = loop.create_task(main(unit_pages=page_count))
            a = loop.run_until_complete(task)
            task.cancel()
            if a:
                return a
    logger.warn('Retry limit exceeded! Giving up...')


def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' % (stage, curtime))


@register_importer
class NewTprTwoImporter(Importer):
    # Importer class dependant attributes:
    name = "newtprtwo"  # Command calling name.
    supported_languages = ['fi', 'sv', 'en']  # Base file requirement.

    def iterator(self, data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        ''' 
        Main class data logic. Create DB objects & set class attributes.
        This was created with easy expandability of the setup data dictionary in mind.
        We are using save() throughout this program to avoid race conditions with update_or_create()
        '''
        for idx, sub_key in enumerate(data[key]):
            try:
                q_obj = query()
                for count, attr in enumerate(obj_model):
                    setattr(q_obj, attr, data[key][sub_key][count])
                q_obj.save()
                setattr(self, attr_map[idx], query.objects.get(
                    id=data[key][sub_key][0]))
                keyfinder = '%s_%s' % (key, sub_key)
                for t_key in data['funcargs']['terms']:
                    for sub_t_key in data[t_key]:
                        if data[t_key][sub_t_key][-1] == keyfinder:
                            data[t_key][sub_t_key][-1] = getattr(
                                self, attr_map[idx])
            except Exception as e:
                logger.error(e)

    def setup(self) -> None:
        self.data = {
            # Public organization, PTV and OSM data_source.
            'ds': {
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
                'tpr': ('tpr', 'Ulkoa tuodut paikkatiedot toimipisteille', True),
            },
            # Public organization class for all instances.
            'orgclass': {
                'paikka': ['org:12', '12', 'Paikkatieto', BaseModel.now(), 'ds_org'],
            },
            # General ontology organization for keywords.
            'org': {
                'tpr': ['tpr:1100', '1100', 'Toimipisterekisteri', BaseModel.now(), 'org:12', 'ds_tpr'],
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_tpr'),
                'orgclass': ('organization_class_12', ),
                'org': ('organization', ),
            },
            # Models for easy iteration (Selected attributes):
            'model_maps': {
                'ds': ('id', 'name', 'user_editable'),
                'orgclass': ('id', 'origin_id', 'name', 'created_time', 'data_source_id'),
                'org': ('id', 'origin_id', 'name', 'created_time', 'classification_id', 'data_source_id'),
            },
            # Function arguments.
            'funcargs': {
                'terms': ('ds', 'orgclass', 'org'),
                'termobjs': (DataSource, OrganizationClass, Organization)
            },
        }
        # Keys in data share per element relevant information. Bring together element per key in data dict for iterator params.
        mapped = list(map(lambda f, fto, mm, atm: [f, fto, self.data['model_maps'][mm], self.data['attr_maps'][atm]],
                      self.data['funcargs']['terms'], self.data['funcargs']['termobjs'], self.data['model_maps'], self.data['attr_maps']))
        # Call the iterator function. Params use the mapped elements.
        for args in mapped:
            self.iterator(
                data=self.data, key=args[0], query=args[1], obj_model=args[2], attr_map=args[3])
        proc_time_frmt('Setup')
        self.handle()

    def __multilang_validator(self, field_name: dict) -> bool:
        # Validator specific method for validating multilang json objects.
        ml_pass = False
        for lang in self.supported_languages:
            lang_val = field_name.get(lang, None)
            if isinstance(lang_val, str):
                lang_val = strip_tags(lang_val)
                if len(lang_val.strip()):
                    field_name[lang] = lang_val
                    if not ml_pass:
                        ml_pass = True
        return ml_pass

    def validate_fields(self, fields: dict) -> None:
        '''
        Fields id, name and either one of street addresses or location coordinate datas are the absolute minimum requirements.
        '''
        id_pass = name_pass = street_address_pass = location_pass = False

        # Validate & format Unit ID.
        if fields['id'] > -1:
            # We assume unit IDs start from 0 and move up.
            fields['id'] = "tpr:%s" % fields['id']
            id_pass = True

        # Validate & format unit name.
        if fields['name']:
            name_pass = self.__multilang_validator(field_name=fields['name'])

        #Validate & format unit street addresses.
        if fields['street_address']:
            street_address_pass = self.__multilang_validator(field_name=fields['street_address'])

        # Validate unit coordinate data & re-format location to serve coordinate data.
        if fields['location']:
            vec2 = [0]*2 # 2D Vector coordinate template.
            coords = fields['location'].get('coordinates', None)
            if isinstance(coords, type(vec2)):
                if len(coords) == len(vec2):
                    if all(isinstance(coords[i], (float, int)) for i in range(len(coords))):
                        '''
                        TPR (Palvelukartta units) coordinates are pre-serialized to (4326 - WGS 84).
                        Transform the coordinates to the default database supported SRID.
                        '''
                        pnt = Point(coords[0], coords[1], srid=4326)
                        pnt.transform(CoordTransform(SpatialReference(4326), SpatialReference(settings.PROJECTION_SRID)))
                        fields['location'] = pnt
                        location_pass = True

        if id_pass and name_pass and street_address_pass or location_pass:
            return {'street_address_pass': street_address_pass, 'location_pass': location_pass}

    def get_json_fields(self, unit: dict) -> dict:
        # Which fields do we want from the API?
        fields = {
            'id': -1,
            'name': {},
            'street_address': {},
            'municipality': '',
            'location': {},
        }
        for field, field_value in fields.items():
            unit_field = unit.get(field, None)
            # Small type validation for the validate_fields section.
            if isinstance(unit_field, type(field_value)):
                fields.update({field: unit_field})
        return fields

    def singular_request(self, muni, address, query, lang) -> Any:
        # We can make an equal match like so:
        address = "%s, %s" % (address, muni.capitalize())
        try:
            # Make an exact match since we have the full format.
            return query.get(**{"name_%s" % lang: address})
        except (MultipleObjectsReturned, ObjectDoesNotExist):
            # Might have a slim chance that duplicates are returned.
            pass

    def regex_contains(self, query, lang, address) -> Any:
        # 23x faster than __contains because of the SQL ~ operator rather than LIKE.
        return query.filter(**{"name_%s__regex" % lang: r'^%s' % address})

    def coord_approx(self, pnt, query, rng=200) -> Any:
        # Approximates the closest address to a point within a specified range.
        return query.annotate(distance=Distance('position', pnt, spheroid=True)).filter(distance__lte=rng).order_by("distance").first()

    def __multilang_iterate(self, func, **kwargs):
        # API supports 3 languages:
        for lang in ('fi', 'sv', 'en'):
            # API language names do not matter at all due data quality issues.
            has_street_lang = kwargs['address'].get(lang, None)
            if has_street_lang:
                tmp = kwargs['address']
                kwargs['address'] = has_street_lang
                for iter_lang in self.supported_languages:
                    # Search the language object against supported languages.
                    kwargs['lang'] = iter_lang
                    val = func(**kwargs)
                    if val:
                        return {'found': val, 'found_lang': iter_lang}
                kwargs['address'] = tmp


    def cnn_matcher(self, strconv: str, mp_type='fit', mp_size=6, fit_len=None) -> list:
        # Convolutional Neural Network Similarity Metric.
        def __kernel_map(mp: int) -> None:
            return [[data[(mp*y)+x] if (mp*y)+x < len(data) else 0 for x in range(mp)] for y in range(mp)]

        data = list(bytes(strconv, "utf-8")) # Convert to bytes.

        # Calculate square value size for the kernel matrix and map the data.
        if mp_type == 'fit':
            for mp in range(10):
                if not fit_len:
                    fit_len = len(data)
                if mp * mp >= fit_len:
                    kernel = __kernel_map(mp=mp)
                    break
        else:
            kernel = __kernel_map(mp=mp_size)

        # Filter matrix.
        filter_mat = (
            (1, 0, 1),
            (0, 1, 0),
            (1, 0, 1),
        )

        # Filter column & row fitting. Check how many placements can be made.
        mat_fit_x = (len(kernel[0]) - len(filter_mat[0])) + 1
        mat_fit_y = (len(kernel) - len(filter_mat)) + 1

        # Construct the size of the output matrix.
        output = [[0 for x in range(mat_fit_x)] for y in range(mat_fit_y)]

        for mxf_y in range(mat_fit_y):
            for mxf_x in range(mat_fit_x):
                for y in range(len(filter_mat)):
                    for x in range(len(filter_mat[0])):
                        calc = kernel[(mxf_y + y)][(mxf_x + x)] * filter_mat[y][x]
                        if calc >= 1:
                            output[mxf_y][mxf_x] += calc
        return output

    def process(self, obj_list: dict) -> None:
        valids = tots = 0
        qset = Place.objects.filter(data_source__id="osoite")
        for idx, units in enumerate(obj_list, start=1):
            logger.info('Page: %s was processed.' % idx)
            for unit in units:
                tots += 1
                data = self.get_json_fields(unit=unit) # Get all fields & construct dict.
                # Validate to make sure we can process this unit:
                geo_pack = self.validate_fields(fields=data)
                if geo_pack:
                    if geo_pack['street_address_pass']:
                        # Data originates from MDS and has human mapped data which is never 100% parseable due to data quality issues.
                        data_sr = data_regx = copy.deepcopy(data)
                        db_street_found = self.__multilang_iterate(self.singular_request, muni=data_sr['municipality'], address=data_sr['street_address'], query=qset, lang=None)
                        if db_street_found:
                            # A valid street address has been found and can be added to que.
                            logger.info('Found -> %s', db_street_found)
                            valids += 1
                        else:
                            '''
                            We can do a regex contain search:
                            This will make a direct match as well but it will 'contain' whatever is passed. 
                            So we're likely to iterate through units with no street numbers.
                            '''
                            regx_filter = self.__multilang_iterate(self.regex_contains, query=qset, lang=None, address=data_regx['street_address'])
                            if regx_filter:
                                # Use a similarity metric to determine the closest sort. (Decided to make my own).
                                filter_results = regx_filter['found']
                                if len(filter_results) > 1:
                                    longest_addr = max(len(addr.name_fi) for addr in filter_results)
                                    for addrs in filter_results:
                                        outpt = self.cnn_matcher(strconv=addrs.name_fi, mp_type='fit', fit_len=longest_addr)
                                        print(outpt, longest_addr)

                                
                                logger.info("%s -> %s" % (data['street_address'], regx_filter['found'][0]))
        logger.info("%s out of %s" % (tots, valids))

    def handle(self) -> None:
        obj_list = async_main()
        self.process(obj_list=obj_list)
        proc_time_frmt('Importer')

        '''
        1) Data gets imported from Turku palvelukartta. The data originates from 
        MDS and is manually filled by humans, therefore the data quality might not be the best.
    
        2) I've added validators to make sure nothing malicious and un-processable can pass through the importer.

        3) Then I make sure we make a direct match.

        4) If nothing is found, I make a regex comparison search and from that I will parse the closest matched address.
        This might need a similarity metric if parsing is flawed.
        Some units do not import municipalities, so I will manually fill in an address from a specific municipality.
        This is because we need accurate data and unique identifiers between different places to avoid duplicates between
        place APIs.
        '''