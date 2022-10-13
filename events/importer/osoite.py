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
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from queue import Empty, Queue
from threading import Thread

# Django:
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import DataSource, BaseModel, Place
from events.importer.util import get_search_column
from .base import Importer, register_importer
from django.utils.html import strip_tags
from django.conf import settings
from django.db import transaction
from django.contrib.gis.gdal import SpatialReference, CoordTransform
from django.contrib.postgres.search import SearchVector


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

# Determines how many threads are run simultaneously when importing places.
THREAD_POOL_SIZE = 8

MUNICIPALITIES = { 
    # Code, municipality_id, name_fi, name_sv
    19: ("aura","Aura", "Aura"),
    202: ("kaarina","Kaarina", "S:t Karins"),
    284: ("koski_tl", "Koski Tl", "Koskis"),
    304: ("kustavi", "Kustavi", "Gustavs"),
    322: ("kemiönsaari", "Kemiönsaari", "Kimitoön"),
    400: ("laitila", "Laitila", "Letala"),
    423: ("lieto", "Lieto", "Lundo"),
    430: ("loimaa", "Loimaa", "Loimaa"),
    445: ("parainen", "Parainen", "Pargas"),
    480: ("marttila", "Marttila", "S:t Mårtens"),
    481: ("masku", "Masku", "Masko"),
    503: ("mynämäki", "Mynämäki", "Virmo"),
    529: ("naantali", "Naantali", "Nådendal"),
    538: ("nousiainen", "Nousiainen", "Nousis"),
    561: ("oripää", "Oripää", "Oripää"),
    577: ("paimio", "Paimio", "Pemar"),
    631: ("pyhäranta", "Pyhäranta", "Pyhäranta"),
    636: ("pöytyä", "Pöytyä", "Pöytis"),
    680: ("raisio", "Raisio", "Reso"),
    704: ("rusko", "Rusko", "Rusko"),
    734: ("salo", "Salo", "Salo"),
    738: ("sauvo", "Sauvo", "Sagu"),
    761: ("somero", "Somero", "Somero"),
    833: ("taivassalo", "Taivassalo", "Tövsala"),
    853: ("turku", "Turku", "Åbo"),
    895: ("uusikaupunki", "Uusikaupunki", "Nystad"),
    918: ("vehmaa", "Vehmaa", "Vemo"),   
}
# Per module logger
logger = logging.getLogger(__name__)
BASE_URL = "https://testipalvelukartta-api.turku.fi/api/v2/address/"
# The source data is serializer into 4326
SOURCE_DATA_SRID = 4326
SOURCE_SRS = SpatialReference(SOURCE_DATA_SRID)
TARGET_SRS = SpatialReference(settings.PROJECTION_SRID)
# 1000 is the max page size in munigeo
PAGE_SIZE = 1000

def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' % (stage, curtime))


@register_importer
class OsoiteImporter(Importer):
    # Importer class dependant attributes:
    name = "osoite"  # Command calling name.
    start_time = None
    places_imported = 0
    supported_languages = ('fi', 'sv', 'en')  # Base file requirement.
    coord_transform = CoordTransform(SOURCE_SRS, TARGET_SRS)
    retry_strategy = Retry(
        total=10,
        status_forcelist=[408, 429, 500, 502, 503, 504],
        method_whitelist=[
            "GET",
        ],
        backoff_factor=40,  # 20, 40, 80, 160, 320, 640, 1280...seconds
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_maxsize=THREAD_POOL_SIZE)
    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)

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
                'osoite': ('osoite', 'Ulkoa tuodut osoitetiedot (sis. paikan)', True),
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
            },
            # Public organization class for all instances.
            'orgclass': {
                'paikka': ('org:12', '12', 'Paikkatieto', BaseModel.now(), 'ds_org'),                
            },
            # General ontology organization for keywords.
            'org': {
                'osoite': ('osoite:1000', '1000', 'Osoiterekisteri', BaseModel.now(), 'org:12', 'ds_osoite'),                
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_org', ),
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

    def index_search_columns(self):
        for lang in self.supported_languages:
            key = "search_column_%s" % lang
            logger.info(
                f"{lang} Places indexed: {Place.objects.update(**{key: get_search_column(Place, lang)})}"
            )

    def get_is_municipality_in_source_data(self, municipality_id):
        request_url = f"{BASE_URL}?municipality={municipality_id}&page_size=1"
        response = requests.get(request_url)
        # requesting with a non existing municipality returns 400 Bad Request.
        if response.status_code == 400:
            return False
        else: 
            # Network and server errors are handled in the retry strategy.           
            return True

    def get_count(self, url):
        url += "&page_size=1"
        response = self.http.get(url)        
        count = response.json()["count"]
        return count     

    def fetch_page(self, url, page):
        request_url = f"{url}&page={page}&page_size={PAGE_SIZE}"
        logger.info(f"Fetching page {page} from {request_url}")
        response = self.http.get(request_url)
        results = response.json()["results"]
        return results
    
    def worker(self, page_queue, results_queue, url):
        while not page_queue.empty():
            try:
                page = page_queue.get_nowait()
            except Empty:
                break
            try:
                results = self.fetch_page(url, page)
            except Exception as err:
                results_queue.put(err)
            else:
                results_queue.put(results)
            finally:
                page_queue.task_done()

    def get_position(self, result):
        lon = None
        lat = None
        try:
            lon = result["location"]["coordinates"][0]
            lat = result["location"]["coordinates"][1]
        except KeyError:
            return None

        position = Point(lat, lon, srid=SOURCE_DATA_SRID)
        position.transform(self.coord_transform)
        return position


    @transaction.atomic
    def save_page(self, results, municipality):
        municipality_id = municipality[0]
        municipality_name = {"fi": municipality[1]}
        municipality_name["sv"] = municipality[2]
        municipality_name["en"] = municipality[1]

        for result in results:
            full_name = {lang:result["full_name"][lang] for lang in self.supported_languages}

            origin_id = f"{full_name['fi'].replace(' ','_')}_{municipality_id}".lower() 
            id = f"osoite:{origin_id}"                   
            entry = {"id":id}
            for lang in self.supported_languages:
                entry["name_" + lang] = f"{full_name[lang]}, {municipality_name[lang]}"
                entry["street_address_" + lang] = full_name[lang]
                entry["address_locality_" + lang] = municipality_name[lang]
            
            entry["origin_id"] = origin_id
            entry["created_time"] = BaseModel.now()
            entry["position"] = self.get_position(result)
            entry["data_source_id"] = getattr(self, "data_source")
            entry["publisher_id"] = getattr(self, "organization").id     
            place = Place(**entry) 
            place.save()
        len_results = len(results)
        logger.info(f"Page saved with {len_results} Places.")
        self.places_imported += len_results       

    def import_municipality(self, municipality): 
        # contains the page numbers to fetch
        page_queue = Queue()
        # contains the results fetched
        results_queue = Queue()       
        url = f"{BASE_URL}?municipality={municipality[0]}"
        count = self.get_count(url)
        num_pages = int(count / PAGE_SIZE) + 1
        logger.info(f"Fetching municipality:{municipality[1]}")
        logger.info(f"Number of pages to fetch: {num_pages} with page size: {PAGE_SIZE}.")
        
        for pool in range(0, num_pages, THREAD_POOL_SIZE):
            threads = []
            # Create threads to the pool
            for page in range(1, THREAD_POOL_SIZE + 1):
                page_number = page + pool
                if page_number <= num_pages:
                    page_queue.put(page_number)
                    threads.append(
                        Thread(
                            target=self.worker,
                            args=(page_queue, results_queue, url),
                        )
                    )

            for thread in threads:
                thread.start()
            page_queue.join()
            while threads:
                threads.pop().join()
            while not results_queue.empty():
                results = results_queue.get()
                if not isinstance(results, Exception):
                    self.save_page(results, municipality)
                else:
                    raise results
      
            end_time = datetime.now()
            duration = end_time - self.start_time
            output_rate = self.places_imported / duration.total_seconds()
            logger.info(f"Duration: {str(duration)[:7]}, Places imported {self.places_imported} ")
            logger.info(f"Output rate(places/second): {round(output_rate,2)}")
 
    def import_places(self):
        # Disable sending signals for the model, as it would cause too much overhead.
        # Instead populate the search columns after the import is finished.
        Place._meta.auto_created = True
        self.start_time = datetime.now()
        for municipality in MUNICIPALITIES.values():
            # Check if municipality exist in the source data.
            if self.get_is_municipality_in_source_data(municipality[0]):
                # Delete only if data_source_id is "osoite", leave "ptv" and "osm" places.
                Place.objects.filter(id__endswith=municipality[0], data_source_id="osoite").delete()
                self.import_municipality(municipality)   
            else:
                logger.warning(f"municipality_id {municipality[0]} not found in source data, skipping.")         
        logger.info("Indexing search columns...")
        self.index_search_columns()        
        # Enable sending signals for the model
        Place._meta.auto_created = True
     
    def handle(self) -> None:
        self.import_places()        
        logger.info(f"Imported {self.places_imported} Places.")
        proc_time_frmt('Importer')

