# -*- coding: utf-8 -*-

# Dependencies:
import math
import time
import logging

# Django:
from .base import Importer, register_importer
from django.core.management import call_command
from events.models import Sidefield

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
class HelptextsImporter(Importer):
    # Importer class dependant attributes:
    name = 'helptexts'
    supported_languages = ('fi', 'sv', 'en')

    # Extra options.
    ignore_setup = True
    ignore_prerequisites = True

    def __init__(self, options):
        proc_time_frmt('Setup')
        sidefield_object = Sidefield()