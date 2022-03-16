# -*- coding: utf-8 -*-

# Dependencies.
import requests
import dateutil
import asyncio
import aiohttp
import logging
import operator
import difflib
import string
import math
import time
import pytz
import json
import copy
import sys
import re

# requires langdetect package.
from langdetect import detect, detect_langs

#datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

# Django:
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import DataSource, BaseModel, Place
from .base import Importer, register_importer
from django.utils.html import strip_tags
from django.conf import settings
from django.db.models.functions import Length

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
    logger.warn('Retry limit exceeded! Giving up...')


def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' % (stage, curtime))


@register_importer
class NewTprThreeImporter(Importer):
    # Importer class dependant attributes:
    name = "newtprthree"  # Command calling name.
    supported_languages = ('fi', 'sv', 'en')  # Base file requirement.

    def iterator(self, data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        ''' 
        Main class data logic. Create DB objects & set class attributes.
        This was created with easy expandability of the setup data dictionary in mind.
        We are using save() throughout this program to avoid race conditions with update_or_create()
        '''
        attrs = iter(attr_map)
        for sub_key in data[key].values():
            q_obj = query()
            for cur_val_idx, current_value in enumerate(sub_key):
                for t_key in data['funcargs']['terms']:
                    for idx, sub_t_key in enumerate(data[t_key]):
                        key_to_find = "%s_%s" % (t_key, sub_t_key)
                        if current_value == key_to_find:
                            current_value = getattr(self, data['attr_maps'][t_key][idx])
                setattr(q_obj, obj_model[cur_val_idx], current_value)
            q_obj.save()
            setattr(self, next(attrs), q_obj)

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
        '''
        Validator specific method for validating multilang json objects.
        Also cleans and formats data.
        '''
        ml_pass = False
        for lang in ('fi', 'sv', 'en'):
            lang_val = field_name.get(lang)
            if isinstance(lang_val, str):
                lang_val = ' '.join(strip_tags(lang_val).replace('\r\n', ' ').split())
                if len(lang_val.strip()):
                    field_name[lang] = lang_val
                    if not ml_pass:
                        ml_pass = True
        return ml_pass

    def __multilang_remove_duplicates(self, field_name: dict) -> None:
        existing = []
        for lang, val in field_name.items():
            if not val in existing:
                existing.append(val)
            else:
                field_name[lang] = None

    def get_json_fields(self, unit: dict) -> int:
        dtypes = {'id': int, 'name': dict, 'street_address': dict, 'municipality': str, 'location': dict} # Basic 'expected' data types for each field.
        data = {(val if isinstance(unit.get(val), valtype) else None): unit.get(val) for val, valtype in dtypes.items()} # Creates the template.
        if data.get('id') and data.get('name') and data.get('street_address') or data.get('location'):
            has_street = has_location = None

            # Validate & format Unit ID.
            if not data['id'] > -1:
                # We assume unit IDs start from 0 and move up.
                return

            # Validate & format name.
            if not self.__multilang_validator(field_name=unit['name']):
                # We assume name isn't just an empty dict and contains valid data.
                return
            else:
                # Remove duplicates.
                self.__multilang_remove_duplicates(field_name=unit['name'])


            # Validate & parse street address into usable form.
            if data.get('street_address'):
                if self.__multilang_validator(field_name=unit['street_address']):
                    # We assume street_name isn't just an empty dict and contains valid data.
                    has_street = True

            # Validate & re-assign location.
            if data.get('location'):
                vec2 = [0]*2 # 2D Vector coordinate template.
                coords = data['location'].get('coordinates', None)
                if isinstance(coords, type(vec2)):
                    if len(coords) == len(vec2):
                        if all(isinstance(coords[i], (float, int)) for i in range(len(coords))):
                            '''
                            TPR (Palvelukartta units) coordinates are pre-serialized to (4326 - WGS 84).
                            Transform the coordinates to the default database supported SRID.
                            '''
                            pnt = Point(coords[0], coords[1], srid=4326)
                            pnt.transform(CoordTransform(SpatialReference(4326), SpatialReference(settings.PROJECTION_SRID)))
                            unit['location'] = pnt
                            has_location = True

            # Return the scenario.
            if has_street and has_location:
                return 1
            if has_street:
                return 2

    def numsplit(self, str_to_split):
        # Gets everything before the first number occurance.
        str_processed = ''
        for letter in str_to_split:
            if letter.isdigit():
                return str_processed.strip()
            else:
                str_processed += letter

    def get_addresses(self):
        qset = Place.objects.filter(data_source__id="osoite") # Get all street addresses.
        existing_addresses = {}
        other_addresses = {}
        for address_obj in qset:
            temp = {'fi': None, 'sv': None}
            for lang in ('fi', 'sv'):
                address_lang = getattr(address_obj, 'name_%s' % lang)
                if isinstance(address_lang, str):
                    res = self.numsplit(address_lang)
                    temp.update({lang: res})
            if temp['fi'] and temp['sv'] and temp['fi'] != temp['sv']:
                # Makes finding very easy.
                existing_addresses.update({temp['fi']: [temp['sv'], address_obj.position, address_obj.address_locality]}) # Easy to find.
            if temp['fi'] != temp['sv']:
                other_addresses.update({temp['fi']: [address_obj.position, address_obj.address_locality]})
        return existing_addresses, other_addresses

    def fix_swedish_address(self, unit: dict, existing_addresses: dict) -> None:
        unit_fi_street = unit['street_address'].get('fi')
        unit_muni = unit.get('municipality')
        if unit_fi_street and unit_muni:
            for finnish_street, finnish_street_data in existing_addresses.items():
                if finnish_street in unit_fi_street and unit_muni.capitalize() == finnish_street_data[2]:
                    unit_fi_processed = unit_fi_street.replace(finnish_street, finnish_street_data[0])
                    # Risky replacements which I don't recommend with larger datasets.
                    replacements = {
                        'rakennus': 'byggnad',
                        ' rak ': ' byg ',
                        ' rak.': ' byg.',
                        'porras': 'trappa',
                        'kerros': 'våning',
                        'rappu': 'trappa',
                        'krs': 'vån',
                        'sairaala': 'sjukhus',
                    }
                    for r, v in replacements.items():
                        unit_fi_processed = unit_fi_processed.replace(r, v)
                    unit['location'] = finnish_street_data[1] # Replace with a more 'accurate' position.
                    return unit_fi_processed

    def save_unit(self, data: dict) -> None:
        # devnote: we have to scan name multilang needs to get the service names 
        try:
            # Private method for multilang attribute mapping.
            def __multilang_attr_map(obj: Any, data_key: str, data_field: dict):
                if data_field:
                    first_existing = None
                    for lang, val in data_field.items():
                        if val and not first_existing:
                            first_existing = True
                            setattr(obj, data_key, val)
                        setattr(obj, '%s_%s' % (data_key, lang), val)
            
            # Private save function.
            def _attribute_map(has_tpr: Any) -> None:
                for data_key in ('name', 'description', 'street_address'):
                    __multilang_attr_map(obj=has_tpr, data_key=data_key, data_field=data[data_key])
                has_tpr.telephone = has_tpr.telephone_fi = data['phone']
                has_tpr.address_locality = has_tpr.address_locality_fi = data['municipality']
                has_tpr.postal_code = data['address_zip']
                has_tpr.publisher_id = 'tpr:1100'
                has_tpr.position = data['location']
                has_tpr.email = data['email']
                #has_tpr.last_modified_time = data['last_modified']

            has_tpr = Place.objects.filter(id=data['id']).first()
            if has_tpr:
                # Update existing TPR.
                _attribute_map(has_tpr=has_tpr)
                has_tpr.save()
                logger.info("%s Updated." % data['id'])
            else:
                # Create a new TPR.
                place_obj = Place(data_source=getattr(self, 'data_source_tpr'))
                place_obj.id = data['id']
                _attribute_map(has_tpr=place_obj)
                place_obj.origin_id = data['origin_id']
                place_obj.created_time = BaseModel.now()
                place_obj.save()
                logger.info("%s Saved." % data['id'])
        except Exception as e:
            logger.error(e)


    def process(self, obj_list) -> None:
        # Private method for the final processing phase.
        def __unit_multilang_fill(unit_field: dict) -> dict:
            return {lang: unit_field.get(lang) for lang in ('fi', 'sv', 'en')}

        # Private functon to cut short validation.
        def _validate_to_str(unit: dict, field_to_get: str) -> Any:
            found = unit.get(field_to_get)
            if not found and not isinstance(found, str):
                found = None
            return found

        processed = []
        existing_addresses, other_addresses = self.get_addresses() # Finnish and Swedish street addresses.
        for idx, units in enumerate(obj_list, start=1):
            logger.info('Page: %s was processed.' % idx)
            for unit in units:
                result = self.get_json_fields(unit=unit)
                if result in (1, 2):
                    res = self.fix_swedish_address(unit=unit, existing_addresses=existing_addresses)
                    if res:
                        unit['street_address']['sv'] = res
                    else:
                        # At this point we only care about valid locations.
                        muni = unit.get('municipality')
                        if unit.get('location') and muni:
                            unit_street_fi = unit['street_address'].get('fi')
                            if unit_street_fi:
                                for other_address, other_address_data in other_addresses.items():
                                    if other_address in unit_street_fi and muni.capitalize() == other_address_data[1]:
                                        unit['location'] = other_address_data[0]
                                        break
                    unit_location = unit.get('location')
                    if unit_location:
                        # Final processing before saving.
                        unit_id = "tpr:%s" % unit['id']
                        unit_name = __unit_multilang_fill(unit_field=unit['name'])
    
                        # Fill description:
                        unit_description = None
                        if unit.get('description'):
                            # Parse the description:
                            if self.__multilang_validator(field_name=unit['description']):
                                self.__multilang_remove_duplicates(field_name=unit['description'])
                                unit_description = __unit_multilang_fill(unit_field=unit['description'])

                        # Fill address data and re-validate.
                        unit_address = __unit_multilang_fill(unit_field=unit['street_address'])
                        if unit_address['en']:
                            unit_address['en'] = None
                            # English street names are not supported in Finland. Small re-verification once we remove this.
                            if not unit_address['fi'] and not unit_address['sv']:
                                break

                        # Fill phone data and validate.
                        unit_phone = unit.get('phone')
                        if unit_phone:
                            if isinstance(unit_phone, dict):
                                # Assume it's multilang.
                                if self.__multilang_validator(field_name=unit['phone']):
                                    self.__multilang_remove_duplicates(field_name=unit['phone'])
                                    unit_phone = __unit_multilang_fill(unit_field=unit['phone'])
                            else:
                                unit_phone = ' '.join(strip_tags(str(unit_phone)).replace('\r\n', ' ').split()) # Clean up.

                        '''
                        # Fill in and parse the last modified time.
                        unit_last_modified = unit.get('last_modified_time') # etc. 2020-10-26T09:05:58.085358+02:00
                        if isinstance(unit_last_modified, str):
                            # Convert the string back into a datetime object and replace the timezone information to match BaseModel.now()
                            unit_last_modified = dateutil.parser.parse(unit_last_modified).replace(tzinfo=pytz.utc)
                        else:
                            unit_last_modified = None
                        '''

                        # Fill in the municipality (address locality).
                        unit_municipality = unit.get('municipality')
                        if isinstance(unit_municipality, str):
                            unit_municipality = unit_municipality.capitalize()
                        else:
                            unit_municipality = None

                        # Fill in the zip data (postal).
                        unit_address_zip = _validate_to_str(unit=unit, field_to_get='address_zip')

                        # Fill in the email data.
                        unit_email = _validate_to_str(unit=unit, field_to_get='email')

                        processed_unit_data = {
                            'id': unit_id,
                            'origin_id': unit['id'],
                            'name': unit_name,
                            'description': unit_description,
                            'street_address': unit_address,
                            'location': unit_location,
                            'municipality': unit_municipality,
                            'phone': unit_phone,
                            # 'last_modified': unit_last_modified,
                            'address_zip': unit_address_zip,
                            'email': unit_email,
                        }
                        processed.append(processed_unit_data)
                        #self.save_unit(data=processed_unit_data)

        dupes = {}
        # Scan for duplicates.
        for tpr_data in processed:
            for lang in self.supported_languages:
                cur_name = tpr_data['name'][lang]
                if cur_name in dupes.keys():
                    dupes[cur_name] += 1
                else:
                    dupes.update({cur_name: 0})
        for k, v in dupes.items():
            if v > 0:
                print(k)
    def handle(self) -> None:
        obj_list = async_main()
        self.process(obj_list=obj_list)
        proc_time_frmt('Importer')