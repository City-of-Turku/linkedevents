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

# List of replacements for streets.
REPLACEMENTS = {
    'rakennus': 'byggnad',
    ' rak ': ' byg ',
    ' rak.': ' byg.',
    'porras': 'trappa',
    'kerros': 'våning',
    'rappu': 'trappa',
    'krs': 'vån',
    'sairaala': 'sjukhus',
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


async def fetch(session: Any, URL: str, id: int) -> dict:
    """Gets the data asynchronously."""
    async with session.get(URL) as response:
        data = await response.read()
        json_response = json.loads(data)
        result = json_response.get('results', None)
        if result:
            logger.info("Page %s gathered..." % id)
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
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        tasks = []
        for page_no in range(1, unit_pages+1):
            # Testipalvelukartta needs turku VPN connection.
            URL = "https://testipalvelukartta.turku.fi/api/v2/unit/?page=%s&page_size=100" % page_no
            tasks.append(fetch(session=session, URL=URL, id=page_no))
        try:
            res = await asyncio.gather(*tasks, return_exceptions=False)
            logger.info("Done gathering all page data. Approximated byte size: %s" %
                        sys.getsizeof(res))
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
    url = "https://testipalvelukartta.turku.fi/api/v2/unit"

    try:
        fetch = requests.get(url, headers=HEADERS)
        response = fetch.json()
        count = response["count"]
        calc = math.modf(count/100)

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
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' %
                (stage, curtime))


@register_importer
class TestImporter(Importer):
    # Importer class dependant attributes:
    name = "test_import"  # Command calling name.
    supported_languages = ('fi', 'sv', 'en')  # Base file requirement.

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
            # Public organization class for all instances.
            'orgclass': {
                'paikka': ('org:12', '12', 'Paikkatieto', BaseModel.now(), 'ds_org'),
            },
            # General ontology organization for keywords.
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

    def __multilang_validator(self, field_name: dict) -> bool:
        """
        Validator specific method for validating multilang json objects.
        Also cleans and formats data.
        """
        ml_pass = False
        for lang in ('fi', 'sv', 'en'):
            lang_val = field_name.get(lang)
            if isinstance(lang_val, str):
                lang_val = ' '.join(strip_tags(
                    lang_val).replace('\r\n', ' ').split())
                if len(lang_val.strip()):
                    field_name[lang] = lang_val
                    if not ml_pass:
                        ml_pass = True
        return ml_pass

    def __multilang_remove_duplicates(self, field_name: dict) -> None:
        """Removes all multilanguage duplicates by reference."""
        existing = []
        for lang, val in field_name.items():
            if not val in existing:
                existing.append(val)
            else:
                field_name[lang] = None

    def get_json_fields(self, unit: dict) -> int:
        """Processing phase for getting fields."""
        # Basic 'expected' data types for each field.
        dtypes = {'id': int, 'name': dict, 'street_address': dict,
                  'municipality': str, 'location': dict}
        data = {(val if isinstance(unit.get(val), valtype) else None): unit.get(
            val) for val, valtype in dtypes.items()}  # Creates the template.
        if data.get('id') and data.get('name') and data.get('street_address') or data.get('location'):
            has_street = has_location = None

            # Validate & format Unit ID.
            if not data['id'] > -1:
                # We assume unit IDs start from 0 and move up.
                logger.warn("Unsupported ID for TPR unit: %s" % unit)
                return

            # Validate & format name.
            if not self.__multilang_validator(field_name=unit['name']):
                # We assume name isn't just an empty dict and contains valid data.
                logger.warn("Unsupported name for TPR unit: %s" % unit)
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
                vec2 = [0]*2  # 2D Vector coordinate template.
                coords = data['location'].get('coordinates', None)
                if isinstance(coords, type(vec2)):
                    if len(coords) == len(vec2):
                        if all(isinstance(coords[i], (float, int)) for i in range(len(coords))):
                            """
                            TPR (Palvelukartta units) coordinates are pre-serialized to (4326 - WGS 84).
                            Transform the coordinates to the default database supported SRID.
                            """
                            pnt = Point(coords[0], coords[1], srid=4326)
                            pnt.transform(CoordTransform(SpatialReference(
                                4326), SpatialReference(settings.PROJECTION_SRID)))
                            unit['location'] = pnt
                            has_location = True

            # Return the scenario.
            if has_street and has_location:
                return 1
            if has_street:
                return 2

    def process(self):
        def __format_street(street: str) -> str:
            """Gets everything before the number in a street."""
            if street:
                oref = re.findall(r'[0-9]+', street)
                if oref:
                    s = street.split(oref[0])[0]
                    return s

        logger.info("start")
        # Risky place replacements.
        for idx, units in enumerate(self.obj_list, start=1):
            print(idx)
            for unit in units:
                result = self.get_json_fields(unit=unit)
                if result in (1, 2):
                    finnish_street = __format_street(
                        unit['street_address'].get('fi'))
                    swedish_street = None
                    muni = unit.get('municipality')
                    if finnish_street:
                        # Patch regex errors.
                        for ch in ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '>', '#', '+', '-', '.', '!', '$', '\'']:
                            finnish_street = finnish_street.replace(ch, '')
                        finnish_street = finnish_street.strip()
                        if isinstance(muni, str):
                            muni = muni.upper()
                            if muni in MUNICIPALITIES:
                                muni = MUNICIPALITIES[muni][0]
                        c = Place.objects.filter(data_source_id='osoite', address_locality_fi=muni).filter(
                            **{"name_fi__regex": r'^%s' % finnish_street})[:1]
                        if c:
                            for o in c:
                                swedish_street = __format_street(
                                    street=o.name_sv)
                                if swedish_street:
                                    swedish_street = swedish_street.strip()
                                    swedish_street = unit['street_address']['fi'].replace(
                                        finnish_street, swedish_street)
                                    for r, v in REPLACEMENTS.items():
                                        swedish_street = swedish_street.replace(
                                            r, v)
                        finnish_street = unit['street_address']['fi']
                    print(finnish_street, swedish_street)
        logger.info("end")

    def handle(self) -> None:
        """The core handler function."""
        self.obj_list = async_main()
        self.process()
        proc_time_frmt('Importer')
