# -> Dev notes: 13/08/2020:
#
# Turku Organization importer for importing all Turku Organization data such as Datasources, Organizations, Organization Classes and support for Virtual Events.
# Contains the latest Turku Linkedevents Organization Model.
# Logger implementation added.

# Dependencies
import logging
import os

from django import db
from django.conf import settings
from django.core.management import call_command
from django.utils.module_loading import import_string
from django_orghierarchy.models import Organization
from django_orghierarchy.models import OrganizationClass
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext
from events.models import DataSource, Place
from .sync import ModelSyncher
from .base import Importer, register_importer

if not exists(join(dirname(__file__), 'logs')):
    mkdir(join(dirname(__file__), 'logs'))

__setattr__ = setattr
__iter__ = iter
__next__ = next


logger = logging.getLogger(__name__)

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


@register_importer
class OrganizationImporter(Importer):
    # name and supported_languages are dependencies that the OrganizationImporter class requires.
    name = curFile  # curFile is defined up top. It's the name of this current file.
    supported_languages = ['fi', 'sv']

    '''       #public data source for organisations model
                ds_args1 = dict(id='org', user_editable=True)
                defaults1 = dict(name='Ulkoa tuodut organisaatiotiedot')
                self.data_source, _ = DataSource.objects.get_or_create(defaults=defaults1, **ds_args1)  '''

    '''
        datasources = {
            'system':[dict(id=settings.SYSTEM_DATA_SOURCE_ID, user_editable=True), dict(name='Järjestelmän sisältä luodut lähteet')],
            'organization':[dict(id="org", user_editable=True), dict(name='Ulkoa tuodut organisaatiotiedot')],
            'turku':[dict(id="turku", user_editable=True), dict(name='Kuntakohtainen data Turun Kaupunki')],
            'yksilo':[dict(id="yksilo", user_editable=True), dict(name='Yksityishenkilöihin liittyvä yleisdata')],
            'virtual':[dict(id="virtual", user_editable=True), dict(name='Virtuaalitapahtumat.')]
        }
        
        return_ds = [self.dsquery(keys, DataSource, values) for keys, values in datasources.items()]

        for k, v in datasources.items():
            __setattr__(self, k, v)
            logger.info("DataSource created: "+k)
        '''

    def setup(self):
        # DataSource

        #ds_args1 = dict(id='org', user_editable=True)
        #defaults1 = dict(name='TEST')
        self.data_source, _ = DataSource.objects.update_or_create(defaults=dict(name='TEST2'), **dict(id='org', user_editable=True))

        self.organization = "bla"
        '''
        self.data_source, _ = DataSource.objects.update_or_create(defaults=dict(
            id=settings.SYSTEM_DATA_SOURCE_ID, user_editable=True), **dict(name='Järjestelmän sisältä luodut lähteet'))
        self.data_source_org, _ = DataSource.objects.update_or_create(defaults=dict(
            id='org', user_editable=True), **dict(name='Ulkoa tuodut organisaatiotiedot'))
        self.data_source_turku, _ = DataSource.objects.update_or_create(defaults=dict(
            id='turku', user_editable=True), **dict(name='Test'))
        self.data_source_yksilo, _ = DataSource.objects.update_or_create(defaults=dict(
            id='yksilo', user_editable=True), **dict(name='Yksityishenkilöihin liittyvä yleisdata'))
        self.data_source_virtual, _ = DataSource.objects.update_or_create(defaults=dict(
            id='virtual', user_editable=True), **dict(name='Virtuaalitapahtumat'))
        '''