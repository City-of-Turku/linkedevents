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
from django_orghierarchy.models import Organization, OrganizationClass
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
        return image
    except:
        logger.warn("Image update_or_create did NOT pass: "+ob+" correctly. Argument/Arguments incompatible.")

def get_create_ds(ob, args):
    try:
        ds, _ = DataSource.objects.update_or_create(defaults=args[1], **args[0])
        return ds
    except:
        logger.warn("DataSource update_or_create did NOT pass: "+ob+" correctly. Argument/Arguments incompatible.")


def get_create_organization(ob, args):
    try:
        org, _ = Organization.objects.update_or_create(defaults=args[1], **args[0])
        return org
    except:
        logger.warn("Organization update_or_create did NOT pass: "+ob+" correctly. Argument/Arguments incompatible.")

def get_create_organizationclass(ob, args):
    try:
        orgclass, _ = OrganizationClass.objects.update_or_create(defaults=args[1], **args[0])
        return orgclass
    except:
        logger.warn("OrganizationClass update_or_create did NOT pass: "+ob+" correctly. Argument/Arguments incompatible.")


def process(self):
    #DataSource
    # -> datasources contains all top level datasource objects; no data_source defined. 
    try:
        self.cc_by_license = License.objects.get(id='cc_by')
    except License.DoesNotExist:
        self.cc_by_license = None

    datasources = {
        'img_ds':[dict(id="image", user_editable=True), dict(name='Kuvapankki')],
        'org':[dict(id="org", user_editable=True), dict(name='Ulkoa tuodut organisaatiotiedot')]
    }
    return_ds = [get_create_ds(keys, values) for keys, values in datasources.items()]

    ds_orgs_class = {
        'kvpankkiclass':[dict(origin_id='15', data_source=return_ds[1]), dict(name='Kuvapankki')],
    }
    return_orgclass_ds = [get_create_organizationclass(keys, values) for keys, values in ds_orgs_class.items()]

    rds = return_ds.__iter__()
    rgc = return_orgclass_ds.__iter__()

    org_arr = {
        'image_org':[dict(origin_id='1500', data_source=return_ds[0], classification_id="org:15"), dict(name='Kuvapankki')],
    }
    return_org = [get_create_organization(keys, values) for keys, values in org_arr.items()]
    ro = return_org.__iter__()

    imgs = {
        'img':[dict(license=self.cc_by_license), dict(data_source=return_ds[0], publisher=return_org[0], url='https://kalenteri.turku.fi/sites/default/files/styles/event_node/public/images/event_ext/sadonkorjuutori.jpg')]
    }
    return_img = [get_create_image(keys, values) for keys, values in imgs.items()]
    rdi = return_img.__iter__()

    try:
        return { # -> Class attribute names go here. Could return an already sorted dictionary if need be.
            'data_source': rds.__next__(),
            'data_source_org': rds.__next__(),
            'org_class': rgc.__next__(),
            'organization': ro.__next__(),
            'image_thing': rdi.__next__()
        }
    except:
        logger.warn("Stop iteration error when returning process function items.")


@register_importer
class ImageBankImporter(Importer):
    name = curFile
    supported_languages = ['fi', 'sv']
    def setup(self):
        for k, v in process(self).items():
            print("yes")
            __setattr__(self, k, v)
            logger.info("ImageBankImporter image created: "+k)