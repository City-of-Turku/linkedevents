# -*- coding: utf-8 -*-

# Dependencies:
import re
import time
import math
import logging
import requests
from pathlib import Path
from PIL import Image as pil_image
from glob import glob as glob_open

# Django:
from django import db
from django.conf import settings
from .base import Importer, register_importer
from django.core.management import call_command
from django.utils.module_loading import import_string
from events.models import Image, License, DataSource, BaseModel
from django_orghierarchy.models import Organization, OrganizationClass

# Type checking:
from typing import TYPE_CHECKING, Any, Tuple, List

# Per module logger
logger = logging.getLogger(__name__)


def proc_time_frmt(stage: str) -> None:
    """Formatter for logs."""
    ft = math.modf(time.process_time())
    curtime = float(str(ft[0])[:3])+ft[1]
    logger.info('%s finished after %s seconds from the initial start!' %
                (stage, curtime))


@register_importer
class ImageBankImporter(Importer):
    # Importer class dependant attributes:
    name = 'turku_image_bank'
    supported_languages = ('fi', 'sv')

    def iterator(self, data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        """
        Main class data logic. Create DB objects & set class attributes.
        This was created with easy expandability of the setup data dictionary in mind.
        We are using save() throughout this program to avoid race conditions with update_or_create()
        """
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
        """Setup phase with mapped needed data."""
        self.data = {
            # Image datasource:
            'ds': {
                'org': ('org', 'Ulkoa tuodut organisaatiotiedot', True),
                'image': ('image', 'Kuvapankki', True),
            },
            # Image organizationclass:
            'orgclass': {
                'image': ('org:15', '15', 'Kuvapankki', BaseModel.now(), 'ds_org'),
            },
            # Organizations for images.
            'org': {
                'image': ('image:1500', '1500', 'Kuvapankki', BaseModel.now(), 'org:15', 'ds_image'),
            },
            # Attribute name mapping for all due to class related attributes (ex. data_source and organization are necessary).
            'attr_maps': {
                'ds': ('data_source', 'data_source_image'),
                'orgclass': ('organization_class_15', ),
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

    def save_image(self, img_path) -> None:
        """Generate the actual DB image object."""

        new_image_id = img_path
        queryset = Image.objects.filter(image=new_image_id)

        if not queryset:
            new_image = Image(data_source=getattr(self, 'data_source_image'))
            for props in ('name', 'photographer_name', 'alt_text'):
                setattr(new_image, props, '')
            new_image.license = self.cc_by_license
            new_image.publisher = getattr(self, 'organization')
            new_image.image = new_image_id
            new_image.save()
            logger.info(f"Saved new image ID: {new_image_id}")
        else:
            logger.info(f"The image with the ID: {new_image_id} already exists. There are {queryset.count()} of them. Skipping...")

    def main(self) -> None:
        """Main processing phase."""

        try:
            self.cc_by_license = License.objects.get(id='cc_by')
        except License.DoesNotExist:
            self.cc_by_license = None

        images = glob_open(f"{Path.cwd()}/events/importer/storage/images/*.webp")
        main_path = Path(f"{settings.MEDIA_ROOT}/images")

        for image in images:
            with open(image, 'rb') as img_file:
                img = pil_image.open(img_file)
                img_name = img.filename
                img.save(f"{main_path}/{img_name}")
                self.save_image(img_path=f"images/{img_name}")

    def handle(self) -> None:
        """The core handler function."""
        self.main()
        proc_time_frmt('Processing and saving')
        proc_time_frmt('Importer')
