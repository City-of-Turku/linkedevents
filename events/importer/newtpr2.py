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

    def __multilang_validator(self, field_name) -> Tuple[bool, dict]:
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

    def validate_fields(self, fields) -> None:
        '''
        Fields like id, name and either one of street addresses or location coordinate datas are the absolute minimum requirements.
        '''
        id_pass = name_pass = street_address_pass = location_pass = False

        # Validate & format Unit ID.
        if fields['id'] > -1:
            fields['id'] = "tpr:%s" % fields['id']
            id_pass = True

        # Validate & format unit name.
        if fields['name']:
            name_pass = self.__multilang_validator(field_name=fields['name'])

        # Validate & format unit street addresses.
        if fields['street_address']:
            street_address_pass = self.__multilang_validator(field_name=fields['street_address'])

        # Validate unit coordinate data.
        if fields['location']:
            vec2 = [0]*2 # 2D Vector coordinate template.
            coords = fields['location'].get('coordinates', None)
            if isinstance(coords, type(vec2)):
                if len(coords) == len(vec2):
                    if all(isinstance(coords[i], (float, int)) for i in range(len(coords))):
                        location_pass = True

        if id_pass and name_pass and street_address_pass or location_pass:
            return True

    def get_json_fields(self, unit) -> None:
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

    def process(self, obj_list) -> None:
        for idx, units in enumerate(obj_list, start=1):
            logger.info('Page: %s was processed.' % idx)
            for unit in units:
                data = self.get_json_fields(unit=unit) # Get all fields & construct dict.
                # Validate to make sure we can process this unit:
                if self.validate_fields(fields=data):
                    logger.info("Validated %s" % data['id'])

    def handle(self) -> None:
        obj_list = async_main()
        self.process(obj_list=obj_list)
        proc_time_frmt('Importer')
