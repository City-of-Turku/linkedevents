# -*- coding: utf-8 -*-

# Dependencies.
import requests
import dateutil
import asyncio
import aiohttp
import logging
import math
import time
import pytz
import json
import sys
import re
import string
from datetime import timedelta
from requests.auth import HTTPBasicAuth

# Django:
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import DataSource, BaseModel, Place
from .base import Importer, register_importer
from django.utils.html import strip_tags
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email, URLValidator

# GeoDjango:
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.gdal import SpatialReference, CoordTransform
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point


# Query speed measurement (used if need be).
from django.db import connection, reset_queries

# Type checking:
from typing import TYPE_CHECKING, Any, Tuple, List

# Per module logger
logger = logging.getLogger(__name__)


HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0',
}

# List of supported municipalities.
MUNICIPALITIES = {
    'AURA': ('Aura', 'Aura'),
    'KAARINA': ('Kaarina', 'S:t Karins'),
    'KOSKI TL': ('Koski Tl', 'Koskis'),
    'KUSTAVI': ('Kustavi', 'Gustavs'),
    'KEMIÖNSAARI': ('Kemiönsaari', 'Kimitoön'),
    'LAITILA': ('Laitila', 'Letala'),
    'LIETO': ('Lieto', 'Lundo'),
    'LOIMAA': ('Loimaa', 'Loimaa'),
    'PARAINEN': ('Parainen', 'Pargas'),
    'MARTTILA': ('Marttila', 'S:t Mårtens'),
    'MASKU': ('Masku', 'Masko'),
    'MYNÄMÄKI': ('Mynämäki', 'Virmo'),
    'NAANTALI': ('Naantali', 'Nådendal'),
    'NOUSIAINEN': ('Nousiainen', 'Nousis'),
    'ORIPÄÄ': ('Oripää', 'Oripää'),
    'PAIMIO': ('Paimio', 'Pemar'),
    'PYHÄRANTA': ('Pyhäranta', 'Pyhäranta'),
    'PÖYTYÄ': ('Pöytyä', 'Pöytis'),
    'RAISIO': ('Raisio', 'Reso'),
    'RUSKO': ('Rusko', 'Rusko'),
    'SALO': ('Salo', 'Salo'),
    'SAUVO': ('Sauvo', 'Sagu'),
    'SOMERO': ('Somero', 'Somero'),
    'TAIVASSALO': ('Taivassalo', 'Tövsala'),
    'TURKU': ('Turku', 'Åbo'),
    'UUSIKAUPUNKI': ('Uusikaupunki', 'Nystad'),
    'VEHMAA': ('Vehmaa', 'Vemo'),
}

# Replacement words for the street.
REPLACEMENTS = {
    'rakennus': 'byggnad',
    ' rak ': ' byg ',
    ' rak.': ' byg.',
    'porras': 'trappa',
    'kerros': 'våning',
    'rappu': 'trappa',
    'krs': 'vån',
    'sairaala': 'sjukhus',
    ' talo ': ' hus ',
}

ENCODE_FORMAT = 'ISO-8859-15'

# Text needs to cleaned.
SAFE_REGEX = ['\\', '`', '*', '_', '{', '}', '[', ']',
              '(', ')', '<', '>', '#', '+', '.', '!', '$', '\'', '|']

SAFE_STRINGS = ['\\', '`', '*', '_',
                '{', '}', '[', ']', '<', '>', '\'', '|', '\r\n', '\xa0']


async def fetch(session: Any, URL: str, id: int) -> dict:
    """Gets the data asynchronously."""
    async with session.get(URL, auth=aiohttp.BasicAuth(settings.SMBACKEND_USER, settings.SMBACKEND_PASS)) as response:
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


async def main(unit_pages: int) -> dict:
    """Processing phase for the async request."""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for page_no in range(1, unit_pages+1):
            # Testipalvelukartta needs turku VPN connection.
            URL = "https://testipalvelukartta-api.turku.fi/api/v2/unit/?page=%s&page_size=50" % page_no
            tasks.append(fetch(session=session, URL=URL, id=page_no))
        try:
            res = await asyncio.gather(*tasks, return_exceptions=False)
            return res
        except Exception as e:
            logger.warn(e)
            await asyncio.sleep(1)


def async_main(retry_count=3) -> dict:
    """
    Currently works in 3.6 Python
    Works for both 3.6 and 3.7 Python versions.

    Fetch page_count by calculating page_size 'count'
    by dividing it with default value 20 (servicemap).
    Testipalvelukartta needs turku VPN connection.
    """
    url = "https://testipalvelukartta-api.turku.fi/api/v2/unit"

    try:
        fetch = requests.get(url, headers=HEADERS, auth=(
            settings.SMBACKEND_USER, settings.SMBACKEND_PASS))
        response = fetch.json()
        count = response["count"]
        print(count)
        calc = math.modf(count/50)

        if calc[0] != float(0):
            page_count = int(calc[1]+1)
        else:
            page_count = int(calc[1])
    except Exception as e:
        raise Exception(
            "Something went wrong in the 'page count' pre-processing phase of TPR API: %s" % e)

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
    """Formatter for logs."""
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' %
                (stage, curtime))


@register_importer
class PalvelukarttaUnitsImporter(Importer):
    # Importer class dependant attributes:
    name = "palvelukartta_units"  # Command calling name.
    supported_languages = ('fi', 'sv', 'en')  # Base file requirement.
    importer_start_time = BaseModel.now()

    def iterator(self, data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        """
        Main class data logic. Create DB objects & set class attributes.
        This was created with easy expandability of the setup data dictionary in mind.
        We are using save() throughout this program to avoid race conditions with update_or_create()
        """
        attrs = iter(attr_map)
        for sub_key in data[key].values():
            q_obj = query()
            for cur_val_idx, current_value in enumerate(sub_key):
                for t_key in data['funcargs']['terms']:
                    for idx, sub_t_key in enumerate(data[t_key]):
                        key_to_find = "%s_%s" % (t_key, sub_t_key)
                        if current_value == key_to_find:
                            current_value = getattr(
                                self, data['attr_maps'][t_key][idx])
                setattr(q_obj, obj_model[cur_val_idx], current_value)
            q_obj.save()
            setattr(self, next(attrs), q_obj)

    def setup(self) -> None:
        """Setup phase with mapped needed data."""
        self.data = {
            # Public organization, PTV and OSM data_source.
            'ds': {
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
                'tpr': ('tpr', 'Ulkoa tuodut paikkatiedot toimipisteille', True),
                'ptv': ('ptv', 'Palvelutietovaranto (PTV)', True),
                'osm': ('osm', 'OpenStreetMap (OSM)', True),
            },
            # Public organization class for all places.
            'orgclass': {
                'paikka': ('org:12', '12', 'Paikkatieto', BaseModel.now(), 'ds_org'),
            },
            # Organizations for places.
            'org': {
                'tpr': ('tpr:1100', '1100', 'Toimipisterekisteri', BaseModel.now(), 'org:12', 'ds_tpr'),
                'ptv': ('ptv:5000', '5000', 'PTV', BaseModel.now(), 'org:12', 'ds_ptv'),
                'osm': ('osm:6000', '6000', 'OSM', BaseModel.now(), 'org:12', 'ds_osm'),
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_tpr', 'data_source_ptv', 'data_source_osm'),
                'orgclass': ('organization_class_12', ),
                'org': ('organization', 'organization_ptv', 'organization_osm'),
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

    def __secure_text(self, txt: str) -> None:
        """Method for patching (securing) text."""
        # Remove all unsupported language letters and tags:
        txt = strip_tags(txt.encode(
            ENCODE_FORMAT, 'ignore').decode(ENCODE_FORMAT))
        # Remove extra unsupported letters due to security reasons:
        for letter in txt:
            if letter in SAFE_STRINGS:
                letter = letter.replace(letter, ' ')
        # Make sure no duplicate spaces are found in sentences:
        txt = ' '.join(txt.split()).strip()
        # Nullify empty strings:
        if txt == '':
            txt = None
        return txt

    def __multilang_duplicate_cleanup(self, field: dict, min_len=1, max_len=2000) -> dict:
        """Method for cleaning a multilanguage field from duplicates."""
        dupes = []
        for lang in self.supported_languages:
            if isinstance(field.get(lang), str):
                field[lang] = self.__secure_text(field[lang])
                valid = False
                if isinstance(field[lang], str):
                    if min_len <= len(field[lang]) <= max_len:
                        if field[lang] not in dupes:
                            dupes.append(field[lang])
                            valid = True
                if not valid:
                    field[lang] = None

    def __format_street(self, street_name: str) -> str:
        """Method for getting the street name only."""
        street_num = re.findall(r'[0-9]+', street_name)
        if street_num:
            street_name = street_name.split(street_num[0])[0].strip()
        else:
            street_name = street_name.split(',')[0].strip()
        return street_name

    def build_data(self, unit: dict) -> dict:
        """Validates and builds the data."""
        data = {
            'ID': None,
            'ORIGIN_ID': None,
            'NAME': {'fi': None, 'sv': None, 'en': None},
            'DESCRIPTION': {'fi': None, 'sv': None, 'en': None},
            'STREET_ADDRESS': {'fi': None, 'sv': None, 'en': None},
            'WWW': {'fi': None, 'sv': None, 'en': None},
            'EMAIL': None,
            'POSITION': None,
            'TELEPHONE': None,
            'POST_CODE': None,
            'ADDRESS_LOCALITY': {'fi': None, 'sv': None, 'en': None},
        }

        # Validate ID.
        uid = unit.get('id')
        if not isinstance(uid, bool) and isinstance(uid, int):
            frmt = str(abs(uid))
            if len(frmt) < 100:
                data['ORIGIN_ID'] = str(abs(uid))
                data['ID'] = 'tpr:%s' % data['ORIGIN_ID']

        if not data['ID']:
            logger.error("Skipping unit due to incorrect ID...")
            return None

        # Validate name.
        if isinstance(unit.get('name'), dict):
            self.__multilang_duplicate_cleanup(field=unit['name'], max_len=255)
            if not any(unit['name'].values()):
                return None
            else:
                for lang in self.supported_languages:
                    if unit['name'].get(lang):
                        data['NAME'][lang] = unit['name'].get(lang)

        # Validate description.
        if isinstance(unit.get('description'), dict):
            self.__multilang_duplicate_cleanup(
                field=unit['description'], min_len=3, max_len=2000)
            for lang in self.supported_languages:
                if unit['description'].get(lang):
                    data['DESCRIPTION'][lang] = unit['description'][lang]

        # Gather municipality (for parsing addresses). Palvelukartta units are within our region.
        if isinstance(unit.get('municipality'), str):
            muni = self.__secure_text(txt=unit['municipality'])
            if muni:
                muni = muni.upper()
                if len(muni) <= 30:
                    if muni in MUNICIPALITIES:
                        for idx, lang in enumerate(('fi', 'sv')):
                            data['ADDRESS_LOCALITY'][lang] = MUNICIPALITIES[muni][idx]

        # Validate position:
        if isinstance(unit.get('location'), dict):
            coords = unit['location'].get('coordinates')
            if isinstance(coords, list):
                if len(coords) == 2:
                    if all(isinstance(coords[i], (float, int)) for i in range(len(coords))):
                        """
                        TPR (Palvelukartta units) coordinates are pre-serialized to (4326 - WGS 84).
                        Transform the coordinates to the default database supported SRID.
                        """
                        try:
                            pnt = Point(coords[0], coords[1], srid=4326)
                            pnt.transform(CoordTransform(SpatialReference(
                                4326), SpatialReference(settings.PROJECTION_SRID)))
                            data['POSITION'] = pnt
                        except Exception as e:
                            logger.warn(
                                "Could not instantiate the location: %s" % e)

        # Validate street addresses and map the Swedish address:
        if isinstance(unit.get('street_address'), dict):
            self.__multilang_duplicate_cleanup(
                field=unit['street_address'], min_len=3, max_len=255)
            if isinstance(unit['street_address'].get('fi'), str):
                data['STREET_ADDRESS']['fi'] = unit['street_address']['fi']
                street = self.__format_street(
                    street_name=unit['street_address']['fi'])
                # Prevent regex exploitation:
                for ch in SAFE_REGEX:
                    street = street.replace(ch, '')
                try:
                    addr = Place.objects.filter(data_source_id='osoite', address_locality_fi=data['ADDRESS_LOCALITY']['fi']).filter(
                        **{"name__regex": r'^%s' % street})[:1]
                    if addr:
                        for addr_obj in addr:
                            if isinstance(addr_obj.name_sv, str):
                                street_sv = self.__format_street(
                                    street_name=addr_obj.name_sv)
                                data['STREET_ADDRESS']['sv'] = unit['street_address']['fi'].replace(
                                    street, street_sv)
                                for r, v in REPLACEMENTS.items():
                                    data['STREET_ADDRESS']['sv'] = data['STREET_ADDRESS']['sv'].replace(
                                        r, v)
                                # If the unit has no position, we can give it one.
                                if not data['POSITION']:
                                    data['POSITION'] = addr_obj.position
                except Exception as e:
                    logger.error("Problem filtering place for unit: %s due to: %s" % (
                        data['ORIGIN_ID'], e))

        # Validate website:
        if isinstance(unit.get('www'), dict):
            self.__multilang_duplicate_cleanup(
                field=unit['www'], min_len=3, max_len=1000)
            for lang in ('fi', 'sv', 'en'):
                if isinstance(unit['www'].get(lang), str):
                    try:
                        URLValidator(unit['www'][lang])
                    except ValidationError as e:
                        logger.warn("Improper URL: %s with details: %s" %
                                    (unit['www'][lang], e))
                    else:
                        data['WWW'][lang] = unit['www'][lang]

        # Validate email:
        if isinstance(unit.get('email'), str):
            email = self.__secure_text(txt=unit['email'])
            if 3 <= len(email) <= 254:
                try:
                    validate_email(email)
                except ValidationError as e:
                    logger.warn("Improper email: %s with details: %s" %
                                (email, e))
                else:
                    data['EMAIL'] = email

        # Validate telephone:
        if isinstance(unit.get('connections'), list):
            if len(unit['connections']) >= 1:
                phones = []
                for connection in unit['connections']:
                    if isinstance(connection.get('phone'), str):
                        if connection['phone'] not in phones:
                            phone = self.__secure_text(txt=connection['phone'])
                            if len(phone) <= 128:
                                phones.append(phone)
                                if len('; '.join(phones)) > 128:
                                    logger.warn(
                                        "Too many phone numbers... stopping here.")
                                    phones.remove(phone)
                                    break
                if phones:
                    data['TELEPHONE'] = '; '.join(phones)

        # Validate address_zip (postcode):
        if isinstance(unit.get('address_zip'), str):
            post_code = self.__secure_text(txt=unit['address_zip'])
            if len(post_code) == 5:
                data['POST_CODE'] = post_code

        return data

    def __multilang_map(self, obj: Any, field_name: str, field_val: str) -> None:
        """Method used in saving for mapping multilang values."""
        setattr(obj, field_name, field_val['fi'])
        for lang in ('fi', 'sv', 'en'):
            setattr(obj, "%s_%s" % (field_name, lang), field_val[lang])

    def map_new_fields(self, obj: Any, data: dict) -> None:
        """Gives the object attributes new values."""
        for field in ('description', 'street_address', 'www', 'address_locality'):
            self.__multilang_map(
                obj=obj, field_name=field, field_val=data[field.upper()])
        obj.email = data['EMAIL']
        obj.telephone = data['TELEPHONE']
        obj.postal_code = data['POST_CODE']
        obj.position = data['POSITION']
        obj.publisher_id = 'tpr:1100'

    def save_units(self, unit: dict) -> None:
        """Main saving logic."""
        unit_found = Place.objects.filter(
            data_source__in=['tpr', 'ptv', 'osm']).filter(name=unit['NAME']['fi'])[:1]
        if unit_found:
            for unit_obj in unit_found:
                # Only update the exact ID match unit.
                if unit['ID'] == unit_obj.id:
                    bm_now = BaseModel.now()
                    if (bm_now - unit_obj.last_modified_time) > (bm_now - self.importer_start_time):
                        """
                        If the current object with the specified name did not get modified during import runtime,
                        we can save 'new' data on top of it. Just an extra caution in case 2+ ID duplicates exist.
                        """
                        try:
                            self.map_new_fields(obj=unit_obj, data=unit)
                            unit_obj.save()
                            logger.info(
                                "Saved existing unit: %s with updated data." % unit['ID'])
                        except Exception as e:
                            logger.error(
                                "Could not save unit: %s due to: %s" % (unit['ID'], e))
        else:
            try:
                new_obj = Place(data_source=getattr(self, 'data_source_tpr'))
                new_obj.id = unit['ID']
                new_obj.origin_id = unit['ORIGIN_ID']
                self.__multilang_map(
                    obj=new_obj, field_name='name', field_val=unit['NAME'])
                self.map_new_fields(obj=new_obj, data=unit)
                new_obj.save()
                logger.info("Created new unit: %s with name: %s" %
                            (unit['ID'], unit['NAME']))
            except Exception as e:
                logger.error("Could not create unit: %s due to: %s" %
                             (unit['ID'], e))

    def process(self, data: dict) -> None:
        """Processing phase."""
        for idx, units in enumerate(data, start=1):
            logger.info("%s unit pages processed." % idx)
            for unit in units:
                data = self.build_data(unit=unit)
                if data:
                    self.save_units(unit=data)

    def remove_old_units(self) -> None:
        """Removes all TPR units that did not get updated."""
        tprs = Place.objects.filter(
            data_source__in=['tpr']).iterator(chunk_size=10)
        if tprs:
            bm_now = BaseModel.now()
            for existing_obj in tprs:
                if (bm_now - existing_obj.last_modified_time) > (bm_now - self.importer_start_time):
                    # This means we know that the object did not get updated during runtime.
                    try:
                        logger.info("Removing old unit: %s with name: %s" % (
                            existing_obj.id, existing_obj.name))
                        existing_obj.delete()
                    except Exception as e:
                        logger.error("Could not remove old unit: %s due to: %s" % (
                            existing_obj.id, e))

    def handle(self) -> None:
        """The core handler function."""
        obj_list = async_main()
        proc_time_frmt('Fetching')
        self.process(data=obj_list)
        proc_time_frmt('Processing and saving')
        self.remove_old_units()
        proc_time_frmt('Removing old units')
        proc_time_frmt('Importer')
