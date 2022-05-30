import logging
from django.core.management.base import BaseCommand
from events.models import Place
from events.importer.util import get_search_column

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        for lang in ["fi", "sv", "en"]:
            key = "search_column_%s" % lang       
            logger.info(
                f"{lang} Places indexed: {Place.objects.update(**{key: get_search_column(Place, lang)})}"
            )
      
