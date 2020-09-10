#Dependencies
import logging
import os
from django import db
from django.conf import settings
from django.core.management import call_command
from django.utils.module_loading import import_string
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext
from events.models import Image, License, DataSource
from django_orghierarchy.models import Organization
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


def get_create_image(ob, args):
    try:
        image, _ = Image.objects.update_or_create(defaults=args[1], **args[0])
        return ds
    except:
        logger.warn("Image update_or_create did NOT pass: "+ob+" correctly. Argument/Arguments incompatible.")

def process(self):
    #DataSource
    # -> datasources contains all top level datasource objects; no data_source defined. 
    try:
        self.cc_by_license = License.objects.get(id='cc_by')
    except License.DoesNotExist:
        self.cc_by_license = None

    try:
        self.organization = Organization.objects.get(id='turku:853')
        print("YES.")
    except License.DoesNotExist:
        self.organization = None

    try:
        self.data_source = DataSource.objects.get(id='turku')
        print("Data_Source YES.")
    except DataSource.DoesNotExist:
        self.data_source = None

    imgs = {
        'img':[dict(license=self.cc_by_license), dict(url='https://kalenteri.turku.fi/sites/default/files/styles/event_node/public/images/event_ext/sadonkorjuutori.jpg', publisher=self.organization, data_source='turku')],
    }
    return_img = [get_create_image(keys, values) for keys, values in imgs.items()]
    rdi = return_img.__iter__()

    try:
        return { # -> Class attribute names go here. Could return an already sorted dictionary if need be.
            'first_image': rdi.__next__(),
        }
    except:
        logger.warn("Stop iteration error when returning process function items.")


@register_importer
class ImageBankImporter(Importer):
    name = curFile
    supported_languages = ['fi', 'sv']
    def setup(self):
        for k, v in process(self).items():
            __setattr__(self, k, v)
            logger.info("ImageBankImporter image created: "+k)