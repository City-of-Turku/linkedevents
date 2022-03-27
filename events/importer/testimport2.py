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
    name = "test_import_2"  # Command calling name.
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

    def build_data(self, unit: dict) -> dict:
        data = {
            'ID': None,
            'ORIGIN_ID': None,
            'PUBLISHER_ID': 'tpr:1100',
            'NAME': {'fi': None, 'sv': None, 'en': None},
            'DESCRIPTION': {'fi': None, 'sv': None, 'en': None},
            'STREET_ADDRESS': {'fi': None, 'sv': None, 'en': None},
            'ADDRESS_LOCALITY': {'fi': None, 'sv': None, 'en': None},
            'POSITION': None,
            'EMAIL': None,
            'TELEPHONE': None,
            'POSTAL_CODE': None,
        }

        # Get ID:
        if isinstance(unit.get('id'), int):
            if unit['id'] > 0:
                data['ID'] = 'tpr:%s' % unit['id']
                data['ORIGIN_ID'] = unit['id']

        if not isinstance(data['ID'], str):
            return None

        # Get name:
        if isinstance(unit.get('name'), dict):
            names = []
            for lang in ('fi', 'sv', 'en'):
                name = unit['name'].get(lang)
                if isinstance(name, str):
                    if name not in names and name != '':
                        names.append(name)
                        data['NAME'][lang] = name

        if not any(data['NAME'].values()):
            return None

        # Get descrioption:
        if isinstance(unit.get('description'), dict):
            descriptions = []
            for lang in ('fi', 'sv', 'en'):
                description = unit['description'].get(lang)
                if isinstance(description, str):
                    if description not in descriptions and description != '':
                        descriptions.append(description)
                        description = ' '.join(strip_tags(
                            description).replace('\r\n', ' ').split()).strip()
                        data['DESCRIPTION'][lang] = description

        # Get street address:

    def process(self):
        for _, units in enumerate(self.obj_list, start=1):
            for unit in units:
                data = self.build_data(unit=unit)
                if isinstance(data, dict):
                    print("Valid unit.")

    def handle(self) -> None:
        """The core handler function."""
        self.obj_list = async_main()
        self.process()
        proc_time_frmt('Importer')
