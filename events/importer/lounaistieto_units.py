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


def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' %
                (stage, curtime))


@register_importer
class LounaistietoImporter(Importer):
    # Importer class dependant attributes:
    name = "lounaistieto_units"  # Command calling name.
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
                            current_value = getattr(
                                self, data['attr_maps'][t_key][idx])
                setattr(q_obj, obj_model[cur_val_idx], current_value)
            q_obj.save()
            setattr(self, next(attrs), q_obj)

    def setup(self) -> None:
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

    def fetch(self) -> dict:
        URL = "https://geoserver.lounaistieto.fi/geoserver/service_points/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=service_points%3Apalvelukohteet&outputFormat=application%2Fjson"
        response = requests.get(URL, headers=HEADERS)
        if response.status_code != 200:
            logger.error(
                "Importing failed. Lounaistieto API responded with status_code: %s" % response.status_code)
            return
        json_data = response.json()
        return json_data

    def numsplit(self, str_to_split: str) -> str:
        # Gets everything before the first number occurance.
        str_processed = ''
        for letter in str_to_split:
            if letter.isdigit():
                return str_processed.strip()
            else:
                str_processed += letter

    def validate(self, data: dict) -> dict:
        # Existing addresses.
        osoite_qset = Place.objects.filter(data_source__id='osoite')
        units = {}
        for lounais_unit in data.get('features'):
            props = lounais_unit.get('properties')
            if props:
                validated = {
                    'ds': None,
                    'id': None,
                    'origin_id': None,
                    'kohteen_nimi': None,
                    'location': None,
                    'puhelinnumero': None,
                    'osoite': None,
                    'sahkoposti': None,
                    'verkkosivu': None,
                    'municipality': None,
                    'postcode': None,
                }
                # Validate and specify data source:
                ds = props.get('datalahde')
                if isinstance(ds, str):
                    if ds == 'OpenStreetMap':
                        validated['ds'] = 'osm'
                    elif ds == 'PTV':
                        validated['ds'] = 'ptv'
                    else:
                        logger.warn(
                            "Unsupported data source for Lounaistieto unit: %s" % props)
                        continue
                else:
                    logger.warn(
                        "Data source type is not valid for Lounaistieto unit: %s" % props)
                    continue

                # Validate and format id:
                origin_id = props.get('orig_id')
                if isinstance(origin_id, str):
                    if origin_id != '':
                        validated['id'] = '%s:%s' % (
                            validated['ds'], origin_id)
                        validated['origin_id'] = origin_id
                    else:
                        logger.warn(
                            "Origin ID is an empty string for: %s" % props)
                        continue
                else:
                    logger.warn("Origin ID type is not valid for: %s" % props)
                    continue

                # Validate name, phone, address, email, website:
                strip_fields = ('kohteen_nimi', 'puhelinnumero',
                                'osoite', 'sahkoposti', 'verkkosivu')
                for field in strip_fields:
                    cur_field = props.get(field)
                    if cur_field:
                        validated_field = strip_tags(str(cur_field)).strip()
                        if validated_field != '':
                            validated[field] = validated_field
                if not validated['kohteen_nimi']:
                    logger.warn("Not a valid name for: %s" % props)
                    continue

                if validated['osoite']:
                    # Gets everything before the first number occurance.
                    cur_address = self.numsplit(
                        str_to_split=validated['osoite'])
                    if cur_address:
                        for osoite in osoite_qset:
                            if osoite.name_fi and osoite.name_sv:
                                osoite_fi = self.numsplit(
                                    str_to_split=osoite.name_fi)
                                osoite_sv = self.numsplit(
                                    str_to_split=osoite.name_sv)
                                if osoite_fi and osoite_sv:
                                    if osoite_fi.lower() == cur_address.lower():
                                        cur_address_sv = validated['osoite'].replace(
                                            cur_address, osoite_sv)
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
                                            ' talo ': ' hus ',
                                        }
                                        for rep_fi, rep_sv in replacements.items():
                                            cur_address_sv = cur_address_sv.replace(
                                                rep_fi, rep_sv)
                                        validated.update(
                                            {'osoite_sv': cur_address_sv})
                                        break

                    # Extract, validate and fill finished street data, municipality and postcode
                    splt = validated['osoite'].split(',')
                    if len(splt) > 1:
                        postal_muni = splt[-1].strip()
                        postal_muni_splt = postal_muni.split()
                        if len(postal_muni_splt) > 1:
                            postcode = postal_muni_splt[0]
                            if postcode.isdigit():
                                validated['postcode'] = postcode
                                muni = postal_muni.replace(
                                    postcode, '').strip().lower().capitalize()
                                validated['municipality'] = muni
                                formatted_osoite = validated['osoite'].replace(
                                    splt[-1], '').rstrip(',')
                                validated['osoite'] = formatted_osoite
                                if validated.get('osoite_sv'):
                                    # Replace most municipalities with the swedish counterpart.
                                    muni_replacements = {
                                        'Turku': 'Åbo',
                                        'Parainen': 'Pargas',
                                        'Kemiönsaari': 'Kimitoön',
                                        'Kaarina': 'S:t Karins',
                                        'Naantali': 'Nådendal',
                                        'Pori': 'Björneborg',
                                        'Rauma': 'Raumo',
                                        'Uusikaupunki': 'Nystad',
                                        'Lieto': 'Lundo',
                                        'Paattinen': 'Patis',
                                        'Littoinen': 'Littois',
                                        'Piikkiö': 'Pikis',
                                        'Nousiainen': 'Nousis',
                                    }
                                    if muni in muni_replacements:
                                        validated.update(
                                            {'municipality_sv': muni_replacements[muni]})
                                    validated['osoite_sv'] = validated['osoite_sv'].replace(
                                        splt[-1], '').rstrip(',')

                # Validate and convert location data:
                northing = props.get('latitude')
                easting = props.get('longitude')
                if northing and easting:
                    # Lounaistieto coordinates are already pre-serialized to 3067 SRID. No transformation needed.
                    pnt = Point(easting, northing, srid=3067)
                    validated['location'] = pnt

                units.update({validated['id']: validated})
        return units

    def finalize(self, data: dict) -> None:
        def __map_fields(place_obj: Any, fields: dict) -> Any:
            place_obj.id = fields['id']
            place_obj.name = place_obj.name_fi = fields['kohteen_nimi']
            place_obj.origin_id = fields['origin_id']
            place_obj.position = fields['location']
            place_obj.street_address = place_obj.street_address_fi = fields['osoite']
            place_obj.street_address_sv = fields.get('osoite_sv')
            place_obj.email = fields['sahkoposti']
            place_obj.telephone = fields['puhelinnumero']
            place_obj.info_url = fields['verkkosivu']
            place_obj.address_locality = place_obj.address_locality_fi = fields['municipality']
            place_obj.address_locality_sv = fields.get('municipality_sv')
            place_obj.postal_code = fields['postcode']
            if fields['ds'] == 'osm':
                place_obj.publisher_id = 'osm:6000'
            else:
                place_obj.publisher_id = 'ptv:5000'
            return place_obj

        # Fix existing DB duplicates.
        tpr_ptv_osm = Place.objects.filter(
            data_source__in=['tpr', 'ptv', 'osm'])
        existing = {}
        for existing_unit in tpr_ptv_osm:
            name = existing_unit.name_fi
            if name:
                if name in existing:
                    try:
                        logger.info("Deleting duplicate. %s" %
                                    existing_unit.id)
                        existing_unit.delete()
                    except Exception as e:
                        logger.warn(
                            "Can't delete duplicate (most likely due to existing relations). %s" % e)
                        existing[name].append(existing_unit)
                        pass
                else:
                    existing.update({name: [existing_unit]})

        # Gather all current duplicates.
        new_units = {}
        for unique_id, cur_unit_data in data.items():
            cur_name = cur_unit_data['kohteen_nimi']
            if not cur_name in existing and not cur_name in new_units:
                new_units.update({cur_name: cur_unit_data})
                logger.info("Saving new unit with ID: %s and name: %s" %
                            (unique_id, cur_unit_data['kohteen_nimi']))
                # Create the new unit:
                try:
                    place_obj = Place(data_source=getattr(
                        self, 'data_source_%s' % cur_unit_data['ds']))
                    place_obj = __map_fields(
                        place_obj=place_obj, fields=cur_unit_data)
                    place_obj.save()
                except Exception as e:
                    logger.warn("Could not save the new unit? %s" % e)
            else:
                if cur_name in existing:
                    for obj in existing[cur_name]:
                        if obj.id == unique_id:
                            # Updating existing unit with possibly new data:
                            logger.info("Updating existing ID: %s with name: %s" % (
                                unique_id, cur_unit_data['kohteen_nimi']))
                            try:
                                obj = __map_fields(
                                    place_obj=obj, fields=cur_unit_data)
                                obj.save()
                            except Exception as e:
                                logger.warn(
                                    "Could not update the unit? %s" % e)
                            break
                else:
                    logger.info("Duplicate from the API exists for ID: %s with name: %s" % (
                        unique_id, cur_unit_data['kohteen_nimi']))

    def handle(self) -> None:
        data = self.fetch()
        proc_time_frmt('Fetching')
        units = self.validate(data=data)
        proc_time_frmt('Validation & processing')
        self.finalize(data=units)
        proc_time_frmt('Duplicate checking & saving')
        proc_time_frmt('Importer')
