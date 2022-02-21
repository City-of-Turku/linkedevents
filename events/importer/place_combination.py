# -*- coding: utf-8 -*-

# Dependencies.

# Logging:
from asyncio import DatagramTransport
import logging
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext

# Django:
from django_orghierarchy.models import Organization
from django_orghierarchy.models import OrganizationClass
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from events.models import Keyword, KeywordLabel, DataSource, BaseModel, Language, Place
from django.contrib.gis.gdal import SpatialReference, CoordTransform
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.contrib.gis import gdal

# Importer specific:
import time
import math
import difflib
import requests
from .base import Importer, register_importer

# Type checking:
from typing import TYPE_CHECKING, Any, Tuple, List

# Setup Logging:
if not exists(join(dirname(__file__), 'logs')):
    mkdir(join(dirname(__file__), 'logs'))

logger = logging.getLogger(__name__)  # Per module logger
curFileExt = basename(__file__)
curFile = splitext(curFileExt)[0]
logFile = \
    logging.FileHandler(
        '%s' % (join(dirname(__file__), 'logs', curFile+'.logs'))
    )
logFile.setFormatter(
    logging.Formatter(
        '[%(asctime)s] <%(name)s> (%(lineno)d): %(message)s'
    )
)
logFile.setLevel(logging.DEBUG)
logger.addHandler(
    logFile
)

def connect() -> List:
    # Lounaistieto geoserver API which contains approximately 5.1K places from PTV and OSM.
    url = "https://geoserver.lounaistieto.fi/geoserver/service_points/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=service_points%3Apalvelukohteet&outputFormat=application%2Fjson"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    try: 
        fetch = requests.get(url, headers=headers)
        response = fetch.json()
        return response
    except Exception as e:
        logger.error("Something went wrong while requesting Lounaistieto geoserver API... %s" % e)

def proc_time_frmt(stage: str) -> None:
    # Formatter for logs.
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info("%s finished after %s seconds from the initial start!" % (stage, curtime))


@register_importer
class PlaceCombinationImporter(Importer):
    # Importer class dependant attributes:
    name = "place_combination"  # Command calling name.
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
                'ptv': ('ptv', 'Palvelutietovaranto (PTV)', True),
                'osm': ('osm', 'OpenStreetMap (OSM)', True),
            },
            # Public organization class for all instances.
            'orgclass': {
                'paikka': ['org:12', '12', 'Paikkatieto', BaseModel.now(), 'ds_org'],
            },
            # General ontology organization for keywords.
            'org': {
                'ptv': ['ptv:5000', '5000', 'PTV', BaseModel.now(), 'org:12', 'ds_ptv'],
                'osm': ['osm:6000', '6000', 'OSM', BaseModel.now(), 'org:12', 'ds_osm'],
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_ptv', 'data_source_osm'),
                'orgclass': ('organization_class_12', ),
                'org': ('organization', 'organization_osm'),
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

    def process(self, place: List) -> None:
        # Processing phase.
        address_data = Place.objects.filter(data_source__id="tpr")
        '''
         First, we want to import those lounaistieto places that do not already exist.
         If they exist, we can most likely fix faulty coordinates as well.
        '''
        tpr_names = [tpr.name_fi for tpr in address_data if tpr.name_fi and tpr.name_fi != ""]

        for obj in place["features"]:
            geom = obj.get("geometry", None)
            props = obj.get("properties", None)
            if geom and props:
                coords = geom.get("coordinates", None)
                target_name = props.get("kohteen_nimi", None)
                if target_name and target_name != "" and target_name in tpr_names:
                    if coords:
                        # Dev note: Before I override a new coordinate,
                        # I should check if the tpr place address matches or if it has changed... might cause issues.
                        # If it's a null address, we can just override, if it has an address we can check it.
                        try:
                            pw = Place.objects.get(name_fi=target_name)
                            pw.position = Point(coords[0], coords[1], srid=3067)
                            pw.save()
                            logger.info("Saved new accurate position %s for %s" % (pw.position, target_name))
                        except Exception as e:
                            ''' 
                            This most likely happens when there are 2 of the same. 
                            It is too risky to automate this process, therefore this should be mapped manually. 
                            '''
                            logger.error("Something went wrong while saving new coordinate for: %s with error: %s" % (target_name, e))
                            continue
                datalahde = props.get("datalahde", None)

    def handle(self) -> None:
        # Handler function for passing data between functions. More organized at the cost of more function calls.
        place_data = connect()
        if place_data:
            logger.info("Successfully gathered place data!")
            self.process(place=place_data)

        proc_time_frmt("Importer")
