# -*- coding: utf-8 -*-

# Dependencies.
import requests
import asyncio
import aiohttp
import logging
import math
import time
import json
import sys

# requires langdetect package.
from langdetect import detect, detect_langs

# Django:
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import DataSource, BaseModel, Place
from .base import Importer, register_importer
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
    "User-Agent": "Mozilla/5.0"
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
        for page_no in range(1, unit_pages):
            # Testipalvelukartta needs turku VPN connection.
            URL = 'https://testipalvelukartta.turku.fi/api/v2/unit/?page=%s' % page_no
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
        calc = math.modf(response['count'] / 20)

        if calc[0] != float(0):
            page_count = int(calc[1]+1)
        else:
            page_count = int(calc[1])
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
    logger.warn("Retry limit exceeded! Giving up...")


def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info("%s finished after %s seconds from the initial start!" % (stage, curtime))


@register_importer
class NewTprImporter(Importer):
    # Importer class dependant attributes:
    name = "newtpr"  # Command calling name.
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
        proc_time_frmt("Setup")
        self.handle()

    def singular_request(self, muni, address, query, lang) -> Any:
        if muni:
            # We can make an equal match like so:
            address = "%s, %s" % (address, muni.capitalize())
            try:
                # Make an exact match since we have the full format.
                return query.get(**{"name_%s" % lang: address})
            except:
                # Might have a slim chance that duplicates or some other unknown error gets returned.
                pass

    def coord_approx(self, pnt, query, rng=200) -> Any:
        if pnt:
            # Approximates the closest address to a point within a specified range.
            return query.annotate(distance=Distance('position', pnt, spheroid=True)).filter(distance__lte=rng).order_by("distance").first()

    def regex_contains(self, query, lang, address) -> Any:
        # 23x faster than __contains because of the SQL ~ operator rather than LIKE.
        return query.filter(**{"name_%s__regex" % lang: r'^%s' % address})

    def validate_multilang_json_obj(self, obj) -> str:
        '''
        Validate unit name and address languages.
        We can only support languages: fi, sv and en from the API.
        '''
        for lang in ("fi", "sv", "en"):
            cur_unit_value = obj.get(lang, None)
            if cur_unit_value and cur_unit_value != "":
                return lang, cur_unit_value

    def multilang_search(self, muni, address, query) -> Any:
        for lang in self.supported_languages:
            found = self.singular_request(muni=muni, address=address, query=query, lang=lang)
            if found:
                return found

    def process(self, obj_list) -> None:
        existing_addresses = Place.objects.filter(data_source__id="osoite")
        address_corrections = not_needed = mcs = uns = 0
        data = [] # Will be used to fill the finished parsed data.
        for idx, infos in enumerate(obj_list, start=1):
            logger.info("Page: %s was processed." % idx)
            for info in infos:
                ids = info.get("id", None)
                addresses = info.get("street_address", None)
                location = info.get("location", None)
                municipality = info.get("municipality", None)
                name = info.get("name", None)
                if name:
                    valid_unit_lang, valid_unit_name = self.validate_multilang_json_obj(obj=name)
                    if valid_unit_lang:
                        pnt = None
                        if location:
                            coordinates = location.get("coordinates", [])
                            # Validate 2D vector:
                            if len(coordinates) == 2:
                                # TPR (Palvelukartta units) coordinates are pre-serialized to (4326 - WGS 84).
                                pnt = Point(coordinates[0], coordinates[1], srid=4326)
                                # Transform the coordinates to the default database supported SRID.
                                pnt.transform(CoordTransform(SpatialReference(4326), SpatialReference(settings.PROJECTION_SRID)))
                        if addresses:
                            valid_address_lang, valid_address = self.validate_multilang_json_obj(obj=addresses)
                            if valid_address:
                                '''
                                Usually with unit Swedish addresses, TPR writes them in Finnish which our DB might not have with direct language based requests.
                                Therefore, scan all the languages til a result is found:
                                '''
                                found = self.multilang_search(muni=municipality, address=valid_address, query=existing_addresses)
                                if found:
                                    logger.info("[ DIRECT ]: Direct address found! Finnish: %s -> Swedish: %s" % (found.name_fi, found.name_sv))
                                    if not found.name_sv:
                                        logger.info("[ SV DIRECT ] Couldn't find Swedish address name... getting unit sv address name: %s" % addresses.get("sv", None))
                                else:
                                    # Since we found multiple addresses, we have to filter through and find the closest...
                                    lr = self.regex_contains(query=existing_addresses, lang=valid_address_lang, address=valid_address)
                                    approximated_address = self.coord_approx(pnt=pnt, query=lr, rng=200)
                                    if approximated_address:
                                        logger.info("[ APPROXIMATED ]: %s" % approximated_address)
                        else:
                            logger.warn("[ ADDRESS ] tpr:%s has no addresses? Approximating..." % ids)
                            # We have to filter and approximate through the entire address registry.
                            approximated_address = self.coord_approx(pnt=pnt, query=existing_addresses, rng=200)
                            if approximated_address:
                                logger.info("[ APPROXIMATED ]: %s" % approximated_address)

    def handle(self) -> None:
        obj_list = async_main()
        self.process(obj_list=obj_list)
        proc_time_frmt("Importer")
