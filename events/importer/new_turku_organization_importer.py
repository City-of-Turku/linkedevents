# -> Dev notes: 11/08/2020:
# 
# Add turku organization version 2 prototype.
# Logger will be added later.

#Dependencies
import logging
import os

from django import db
from django.conf import settings
from django.core.management import call_command
from django.utils.module_loading import import_string
from django_orghierarchy.models import Organization
from django_orghierarchy.models import OrganizationClass
from os.path import basename, splitext

from events.models import DataSource, Place
from .sync import ModelSyncher
from .base import Importer, register_importer


__setattr__ = setattr
__iter__ = iter
__next__ = next


logger = logging.getLogger(__name__) 

curFileExt = basename(__file__)
curFile = splitext(curFileExt)[0]

# -> logger TO BE MADE handling here.

def get_create_ds(ob, args):
    try:
        ds, _ = DataSource.objects.get_or_create(defaults=args[1], **args[0])
        return ds #sys_ds "return ds_args, defaults, etc"
    except:
        pass

def get_create_organization(ob, args):
    try:
        org, _ = Organization.objects.get_or_create(defaults=args[1], **args[0])
        return org #sys_ds "return ds_args, defaults, etc"
    except:
        pass

def get_create_organizationclass(ob, args):
    try:
        orgclass, _ = OrganizationClass.objects.get_or_create(defaults=args[1], **args[0])
        return orgclass #sys_ds "return ds_args, defaults, etc"
    except:
        pass

def get_create_place(ob, args): #Function not in use yet.
    try:
        placey, _ = Place.objects.get_or_create(defaults=args[1], **args[0])
        return placey #sys_ds "return ds_args, defaults, etc"
    except:
        pass

def preprocess():
    #DataSources
    ###################################### 
    # -> ds_arr contains all top level datasource objects; no data_source defined. 
    datasources = {
        'system':[dict(id=settings.SYSTEM_DATA_SOURCE_ID, user_editable=True), dict(name='Järjestelmän sisältä luodut lähteet')],
        'org':[dict(id="org", user_editable=True), dict(name='Ulkoa tuodut organisaatiotiedot')],
        'turku':[dict(id="turkuuuuu", user_editable=True), dict(name='Kuntakohtainen data Turuuuuun Kaupunki')],
        'yksilo':[dict(id="yksilo", user_editable=True), dict(name='Yksityishenkilöihin liittyvä yleisdata')],
        'virtual':[dict(id="virtual", user_editable=True), dict(name='Virtuaalitapahtumat (ei paikkaa, vain URL)')]
    }
    return_ds = [get_create_ds(keys, values) for keys, values in datasources.items()]

    # -> ds_sub contains all objects with a data_source component.
    # -> I can't really format this better for example inside the functions at the top because
    # -> return_ds[1] has to be defined within this scope so I can't have a text based list with dict constructed at the top.
    # -> return_ds[1] = org.

    ds_orgs_class = {
        'valt_toim':[dict(origin_id='1', data_source=return_ds[1], user_editable=True), dict(name='Valtiollinen toimija')],
        'maak_toim':[dict(origin_id='2', data_source=return_ds[1], user_editable=True), dict(name='Maakunnallinen toimija')],
        'kunta':[dict(origin_id='3', data_source=return_ds[1], user_editable=True), dict(name='Kunta')],
        'kunnan_liik':[dict(origin_id='4', data_source=return_ds[1], user_editable=True), dict(name='Kunnan liikelaitos')],
        'valt_liik':[dict(origin_id='5', data_source=return_ds[1], user_editable=True), dict(name='Valtion liikelaitos')],
        'yritys':[dict(origin_id='6', data_source=return_ds[1], user_editable=True), dict(name='Yritys')],
        'säätiö':[dict(origin_id='7', data_source=return_ds[1], user_editable=True), dict(name='Säätiö')],
        'seurakunta':[dict(origin_id='8', data_source=return_ds[1], user_editable=True), dict(name='Seurakunta')],
        'yhdseur':[dict(origin_id='9', data_source=return_ds[1], user_editable=True), dict(name='Yhdistys tai seura')],
        'muuyht':[dict(origin_id='10', data_source=return_ds[1], user_editable=True), dict(name='Muu yhteisö')],
        'ykshenk':[dict(origin_id='11', data_source=return_ds[1], user_editable=True), dict(name='Yksityishenkilö')],
        'paiktieto':[dict(origin_id='12', data_source=return_ds[1], user_editable=True), dict(name='Paikkatieto')],
        'sanasto':[dict(origin_id='13', data_source=return_ds[1], user_editable=True), dict(name='Sanasto')],
        'virtuaalitapah':[dict(origin_id='14', data_source=return_ds[1], user_editable=True), dict(name='Virtuaalitapahtuma')],
    }
    return_orgclass_ds = [get_create_organizationclass(keys, values) for keys, values in ds_orgs_class.items()]
    
    # ds_sub needs a datasource get value, hence why return_ds[0] -
    # has to be used after the iteration and two separate iterations are required.
    rds = return_ds.__iter__()
    rgc = return_orgclass_ds.__iter__()
    ######################################

    #Organizations
    ######################################
    org_arr = {
        'turku_org':[dict(origin_id='turku', data_source=return_ds[2], classification_id="org:3"), dict(name='Virtuaalitapahtumat (ei paikkaa, vain URL)')],
        'ykshenkilöt':[dict(origin_id='2000', data_source=return_ds[2], classification_id="org:11"), dict(name='Yksityishenkilöt')],
        'org_virtual':[dict(origin_id='3000', data_source=return_ds[4], classification_id="org:14"), dict(name='Virtuaalitapahtumat')],
    }
    return_org = [get_create_organization(keys, values) for keys, values in org_arr.items()]
    ro = return_org.__iter__()
    ######################################

    place_arr = {
        'place_org_virtual':[dict(origin_id='3000', data_source=return_ds[4], classification_id="org:14"),
        dict(data_source=return_ds[4],
        publisher=return_org[2],
        name='Virtuaalitapahtuma',
        name_fi='Virtuaalitapahtuma',
        name_sv='Virtuell evenemang',
        name_en='Virtual event',
        description='Toistaiseksi kaikki virtuaalitapahtumat merkitään tähän paikkatietoon.')]
    }
    return_place_org = [get_create_place(keys, values) for keys, values in place_arr.items()]
    rpo = return_place_org.__iter__()

    return { # -> Class attribute names go here. Could return an already sorted dictionary if need be.
        'data_source': rds.__next__(),
        'organization': ro.__next__(),
        'data_source_system': rds.__next__(),
        'data_source_org': rds.__next__(),
        'organization_class_1': rgc.__next__(),
        'organization_class_2': rgc.__next__(),
        'organization_class_3': rgc.__next__(),
        'organization_class_4': rgc.__next__(),
        'organization_class_5': rgc.__next__(),
        'organization_class_6': rgc.__next__(),
        'organization_class_7': rgc.__next__(),
        'organization_class_8': rgc.__next__(),
        'organization_class_9': rgc.__next__(),
        'organization_class_10': rgc.__next__(),
        'organization_class_11': rgc.__next__(),
        'organization_class_12': rgc.__next__(),
        'organization_class_13': rgc.__next__(),
        'organization_class_14': rgc.__next__(),
        'organization_1': ro.__next__(),
        'organization_2': ro.__next__(),
        'organization_virtual': rpo.__next__()
    }

#class Thing(object):
@register_importer
class OrganizationImporter(Importer):
    #name and supported_languages are dependencies that the OrganizationImporter class requires.
    name = curFile #curFile is defined up top. It's the name of this current file.
    supported_languages = ['fi', 'sv']
    def setup(self):
        for k, v in preprocess().items():
            __setattr__(self, k, v)
