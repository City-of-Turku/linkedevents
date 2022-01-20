# -*- coding: utf-8 -*-

# Dependencies.

# Logging:
import time
import logging
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext

# Django:
from django_orghierarchy.models import Organization
from django_orghierarchy.models import OrganizationClass
from events.models import DataSource, BaseModel, Keyword

# Importer specific:
from .base import Importer, register_importer

# Type checking:
from typing import Any

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


@register_importer
class TslImporter(Importer):
    # Importer class dependant attributes:
    name = "tsl"  # Command calling name.
    supported_languages = ['fi', 'sv', 'en']  # Base file requirement.

    def iterator(self: 'events.importer.tsl.TslImporter', data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        ''' Main class data logic. Create DB objects & set class attributes.
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

    def save_kw(self: 'events.importer.tsl.TslImporter') -> None:
        try:
            for k, v in self.keywords.items():
                kw = Keyword(data_source=getattr(self, 'data_source'))
                kw.id = k
                kw.publisher = getattr(self, 'organization')
                for lang, lang_val in v.items():
                    langformat = 'name_%s' % lang
                    setattr(kw, langformat, lang_val)
                kw.created_time = BaseModel.now()
                kw.save()
                logger.info("Saved TSL keyword ID: %s" % k)
        except Exception as e:
            logger.error(e)
            pass

    def setup(self: 'events.importer.tsl.TslImporter') -> None:
        ''' 
            This can be used as a template for other importers as it's constructed
            to be very easily expandable. It also avoids race condition issues by utiling save().

            To add a new model we just define it as a key, add the attribute name to attr_maps,
            add the model values to model_maps and add the required values mapped by those
            model_maps within. Remember that the values that are underneath each other
            are creater later than the former so you'd want to follow this mindset throughout the data dict.

            This might look like a static assignment importer but
            we use the magic of setattr to create the necessary objects before assignment.

            Typically we define data_sources to organisations after they have been created,
            but here we don't even have to worry about long update_or_create chains or get chains
            should our data be large. If you take a look at "org", the data_source is defined as
            'ds' followed by '_tsl'. The importer by itself finds the correct data_source when it is
            trying to create the organization 'tsl'.
        '''
        self.data = {
            # TSL and the Public DataSource for Organizations model.
            'ds': {
                'tsl': ('tsl', 'Turun sanalista', True),
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
            },
            # Public organization class for all instances.
            'orgclass': {
                'sanasto': ['org:13', '13', 'Sanasto', BaseModel.now(), 'ds_org'],
            },
            # TSL organization.
            'org': {
                'tsl': ['tsl:3000', '3000', 'TSL', BaseModel.now(), 'org:13', 'ds_tsl'],
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_org'),
                # Tuples get converted to strings for single values if they don't contain , at the end
                'orgclass': ('organization_class_13',),
                'org': ('organization',),
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
        logger.info("Setup finished...")
        self.handle()

    def handle(self: 'events.importer.tsl.TslImporter') -> None:
        logger.info("Gather TSL keywords...")
        self.keywords = tsl()
        logger.info("Saving TSL keywords...")
        self.save_kw()
        logger.info("Importer finished in: %s" % time.process_time())
