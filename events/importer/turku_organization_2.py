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

        self.data_source, _ = DataSource.objects.update_or_create(
            defaults=dict(name='TEST Järjestelmän sisältä luodut lähteet'), **dict(id=settings.SYSTEM_DATA_SOURCE_ID, user_editable=True))
        self.data_source_org, _ = DataSource.objects.update_or_create(
            defaults=dict(name='TEST Ulkoa tuodut organisaatiotiedot'), **dict(id='org', user_editable=True))
        self.data_source_org, _ = DataSource.objects.update_or_create(
            defaults=dict(name='TEST Kuntakohtainen data Turun Kaupunki'), **dict(id='turku', user_editable=True))
        self.data_source_org, _ = DataSource.objects.update_or_create(
            defaults=dict(name='TEST Yksityishenkilöihin liittyvä yleisdata'), **dict(id='yksilo', user_editable=True))
        self.data_source_org, _ = DataSource.objects.update_or_create(
            defaults=dict(name='TEST Virtuaalitapahtumat'), **dict(id='virtual', user_editable=True))
        self.organization = "bla"

        # OrganizationClass

        self.valttoim, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Valtiollinen toimija'), **dict(origin_id='1', data_source=self.data_source_org))
        self.maaktoim, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Maakunnallinen toimija'), **dict(origin_id='2', data_source=self.data_source_org))
        self.kunta, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='TEST Kunta'), **dict(origin_id='3', data_source=self.data_source_org))
        self.kunnanliik, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Kunnan liikelaitos'), **dict(origin_id='4', data_source=self.data_source_org))
        self.valtliik, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Valtion liikelaitos'), **dict(origin_id='5', data_source=self.data_source_org))
        self.yrityss, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Yritys'), **dict(origin_id='6', data_source=self.data_source_org))
        self.saatioo, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Säätiö'), **dict(origin_id='7', data_source=self.data_source_org))
        self.seurakuntaa, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Seurakunta'), **dict(origin_id='8', data_source=self.data_source_org))
        self.yhdseurr, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Yhdistys tai seura'), **dict(origin_id='9', data_source=self.data_source_org))
        self.muuyhtt, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Muu yhteisö'), **dict(origin_id='10', data_source=self.data_source_org))
        self.ykshenkk, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Yksityishenkilö'), **dict(origin_id='11', data_source=self.data_source_org))
        self.paiktietoo, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Paikkatieto'), **dict(origin_id='12', data_source=self.data_source_org))
        self.sanastoo, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Sanasto'), **dict(origin_id='13', data_source=self.data_source_org))
        self.virtuaalitapahh, _ = OrganizationClass.objects.update_or_create(
            defaults=dict(name='Virtuaalitapahtuma'), **dict(origin_id='14', data_source=self.data_source_org))

        self.organization = "bla"
        '''
        ds_orgs_class = {
        'valttoim':[dict(origin_id='1', data_source=return_ds[1]), dict(name='Valtiollinen toimija')],
        'maaktoim':[dict(origin_id='2', data_source=return_ds[1]), dict(name='Maakunnallinen toimija')],
        'kunta':[dict(origin_id='3', data_source=return_ds[1]), dict(name='Kunta')],
        'kunnanliik':[dict(origin_id='4', data_source=return_ds[1]), dict(name='Kunnan liikelaitos')],
        'valtliik':[dict(origin_id='5', data_source=return_ds[1]), dict(name='Valtion liikelaitos')],
        'yrityss':[dict(origin_id='6', data_source=return_ds[1]), dict(name='Yritys')],
        'saatioo':[dict(origin_id='7', data_source=return_ds[1]), dict(name='Säätiö')],
        'seurakuntaa':[dict(origin_id='8', data_source=return_ds[1]), dict(name='Seurakunta')],
        'yhdseurr':[dict(origin_id='9', data_source=return_ds[1]), dict(name='Yhdistys tai seura')],
        'muuyhtt':[dict(origin_id='10', data_source=return_ds[1]), dict(name='Muu yhteisö')],
        'ykshenkk':[dict(origin_id='11', data_source=return_ds[1]), dict(name='Yksityishenkilö')],
        'paiktietoo':[dict(origin_id='12', data_source=return_ds[1]), dict(name='Paikkatieto')],
        'sanastoo':[dict(origin_id='13', data_source=return_ds[1]), dict(name='Sanasto')],
        'virtuaalitapahh':[dict(origin_id='14', data_source=return_ds[1]), dict(name='Virtuaalitapahtuma')],
        }
        '''
