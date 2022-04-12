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
from events.models import BaseModel, PaymentMethod

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
class PMDImporter(Importer):
    # Required super 'base' class dependencies...
    name = "payment_method_defaults"  # Command calling name.
    supported_languages = ('fi', 'sv', 'en')  # Language requirement.
    data_source = organization = None

    def setup(self) -> None:
        # Multilang payment methods:
        data = {
            'KÄTEINEN': {'fi': 'Käteinen', 'sv': 'Kontant', 'en': 'Cash'},
            'MAKSUKORTTI': {'fi': 'Maksukortti', 'sv': 'Betalkort', 'en': 'Charge Card'},
            'VIRIKESETELI': {'fi': 'Virikeseteli', 'sv': 'Fritidssedel', 'en': 'Recreational Voucher'},
            'TYKY-RANNEKE': {'fi': 'Tyky-ranneke', 'sv': 'Tyky-armband', 'en': 'Tyky-bracelet'},
            'VERKKOMAKSU': {'fi': 'Verkkomaksu', 'sv': 'Onlinebetalning', 'en': 'Online Payment'},
            'MOBILE_PAY': {'fi': 'MobilePay', 'sv': 'MobilePay', 'en': 'MobilePay'},
            'MUSEOKORTTI': {'fi': 'Museokortti', 'sv': 'Museikort', 'en': 'Museum Card'},
            'LASKU': {'fi': 'Lasku', 'sv': 'Räkning', 'en': 'Invoice'},
        }

        for idx, words in enumerate(data.values(), start=1):
            try:
                pm = PaymentMethod()
                pm.id = str(idx)
                pm.name = words['fi']
                for lang in self.supported_languages:
                    setattr(pm, 'name_%s' % lang, words[lang])
                logger.info("Saved payment method ID: %s with names: %s" %
                            (idx, words))
                pm.save()
            except Exception as e:
                logger.error(
                    "Error while trying to save payment method data: %s, due to: %s" % (words, e))
