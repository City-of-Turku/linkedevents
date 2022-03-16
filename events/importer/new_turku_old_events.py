# -*- coding: utf-8 -*-

# Dependencies.
from email import header
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
from datetime import datetime, timedelta

# requires langdetect package.
from langdetect import detect, detect_langs

# Django:
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django_orghierarchy.models import Organization, OrganizationClass
from events.models import BaseModel, Event, Keyword, DataSource, Place, License, Image, Language, EventLink, Offer
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

def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' % (stage, curtime))


@register_importer
class NewTprThreeImporter(Importer):
    # Importer class dependant attributes:
    name = "new_turku_old_events"  # Command calling name.
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
            # Datasources.
            'ds': {
                'turku': ('turku', 'Kuntakohtainen data Turun Kaupunki', True),
                'virtual': ('virtual', 'Virtuaalitapahtumat (ei paikkaa, vain URL)', True),
                'tpr': ('tpr', 'Ulkoa tuodut paikkatiedot toimipisteille', True),
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
            },
            # Organization classes for all instances.
            'orgclass': {
                'kunta': ['org:3', '3', 'Kunta', BaseModel.now(), 'ds_org'],
                'virtual': ['org:14', '14', 'Virtuaalitapahtuma', BaseModel.now(), 'ds_org'],
            },
            # Organizations.
            'org': {
                'turku': ['turku:853', '853', 'Turun kaupunki', BaseModel.now(), 'org:3', 'ds_turku'],
                'virtual': ['virtual:3000', '3000', 'Virtuaalitapahtumat', BaseModel.now(), 'org:14', 'ds_virtual'],
            },
            # Virtual place.
            'place': {
                'virtual': [
                    'virtual:public', 'public', 'Virtuaalitapahtuma', 'Virtuaalitapahtuma', 'Virtuell evenemang', 'Virtual event',
                    'Virtuaalitapahtumat merkitään tähän paikkatietoon.', BaseModel.now(), 'org_virtual', 'ds_virtual'
                ],
            },
            # Licenses
            'license': {
                'event': [
                    'event_only', 'Vain tapahtuman markkinointiin', 'Vain tapahtuman markkinointiin', 
                    'Endast för marknadsföring av evenemanget', 'For event marketing only', ''
                ],
                'cc': [
                    'cc_by', 'Nimeä 4.0 Kansainvälinen (CC BY 4.0)', 'Nimeä 4.0 Kansainvälinen (CC BY 4.0)', 
                    'Erkännande 4.0 Internationell (CC BY 4.0)', 'Attribution 4.0 International (CC BY 4.0)',
                    'https://creativecommons.org/licenses/by/4.0/'
                ],
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_virtual', 'data_source_tpr', 'data_source_org'),
                'orgclass': ('organization_class_3', 'organization_class_14'),
                'org': ('organization', 'organization_virtual'),
                'place': ('internet_location', ),
                'license': ('event_only_license', 'cc_by_license'),
            },
            # Models for easy iteration (Selected attributes):
            'model_maps': {
                'ds': ('id', 'name', 'user_editable'),
                'orgclass': ('id', 'origin_id', 'name', 'created_time', 'data_source_id'),
                'org': ('id', 'origin_id', 'name', 'created_time', 'classification_id', 'data_source_id'),
                'place': ('id', 'origin_id', 'name', 'name_fi', 'name_sv', 'name_en', 'description', 'created_time', 'publisher', 'data_source_id'),
                'license': ('id', 'name', 'name_fi', 'name_sv', 'name_en', 'url'),
            },
            # Function arguments.
            'funcargs': {
                'terms': ('ds', 'orgclass', 'org', 'place', 'license'),
                'termobjs': (DataSource, OrganizationClass, Organization, Place, License)
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

    def validate_fields(self, event_fields: dict) -> None:
        '''
        Clean and validate event fields.
        Custom datatypes: many, timestamp and geocoordinate.
        '''

        # Private method for cleaning text.
        def __clean_text(text: str) -> str:
            parsed_text = ' '.join(strip_tags(text).replace('\r\n', ' ').split())
            if parsed_text != '':
                return parsed_text

        # Formats the date into a pytz convertable format.
        def timeToTimestamp(origTime: Any) -> Any:
            timestamp = time.mktime(time.strptime(origTime, '%d.%m.%Y %H.%M'))
            dt_object = datetime.fromtimestamp(timestamp)
            return str(dt_object)

        # Converts the formatted date into a proper UTC datetime object.
        def dt_parse(dt_str: str) -> Any:
            # Times are in UTC+02:00 TZ.
            return pytz.timezone('Europe/Helsinki').localize(
                dateutil.parser.parse(dt_str),
                is_dst=None).astimezone(pytz.utc)

        field_map = {
            'title': str, 'start_date': 'timestamp', 'end_date': 'timestamp', 
            'lead_paragraph_markup': str, 'description': str, 
            'event_type': str, 'drupal_nid': str, 'drupal_nid_super': str,
            'event_categories': 'many', 'target_audience': 'many', 'keywords': 'many',
            'address': str, 'location': 'geocoordinate', 'place': str, 'free_event': str,
            'event_price': str, 'buy_tickets_url': str, 'event_image_ext_url': str,
            'event_image_license': str, 'website_url': str, 'facebook_url': str,
            'twitter_url': str, 'event_organizer': str, 'is_hobby': str,
            }

        for field_map_field, field_map_value in field_map.items():
            for event_field, event_field_value in event_fields.items():
                if field_map_field in event_field:
                    # Clean all regular text fields.
                    if type(event_field_value) == field_map_value:
                        event_fields[event_field] = __clean_text(text=event_field_value)
                    # Format start and end times.
                    if field_map_value == 'timestamp':
                        field_timestamp = timeToTimestamp(origTime=event_fields[event_field])
                        field_dt = dt_parse(dt_str=field_timestamp)
                        event_fields[event_field] = field_dt
                    #if field_map_value == 'many':


    def get_events(self) -> None:
        logger.info("Establishing connection to Turku Drupal API...")
        url = 'https://kalenteri.turku.fi/admin/event-exports/json_beta'
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logger.error("Importing failed. Turku Drupal API responded with status_code: %s" % response.status_code)
            return
        json_data = response.json()

        all_events = {
            'Single event': {},
            'Recurring event (in series)': {},
            'Event series': {}
            }

        for events in json_data['events']:
            for event, event_fields in events.items():
                event_type = event_fields.get('event_type')
                event_id = event_fields.get('drupal_nid')
                if event_id and event_type in all_events.keys():
                    self.validate_fields(event_fields=event_fields)
                    all_events[event_type].update({event_id: event})
        
        print(all_events)
    def handle(self) -> None:
        self.get_events()
        proc_time_frmt('Importer')