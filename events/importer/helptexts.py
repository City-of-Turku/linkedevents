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

data = {
    'location_sidefield': {
        'fi': """Tapahtuma voi olla virtuaalinen, lähitapahtuma tai molemmat. 
        <br><strong>Jos tapahtuma järjestetään etänä internetissä, valitse tapahtumapaikaksi 
        Virtuaalitapahtuma ja syötä URL-osoite. Lähitapahtumassa voit antaa lisätietoja 
        tapahtumapaikan löytämiseksi, esimerkiksi konferenssihuoneen nimen tai ohjeet sisäänkäynnille.</strong><br>
        Jos tarkkaa tapahtumapaikkaa ei löydy listasta, valitse tapahtumapaikaksi lähin katuosoite 
        ja kirjoita paikan nimi tai muut tarkemmat saapumisohjeet tiiviisti lisätietokenttään.""",

        'sv': """Evenemanget kan vara virtuellt, fysiskt eller båda.
        <br><strong>Om evenemanget ordnas på distans över internet, välj då Virtuellt evenemang som evenemangsplats, 
        samt mata in en URL. Du kan ange ytterligare information för att hitta evenemangsplatsen, 
        till exempel konferensrummets namn eller instruktioner för att hitta ingången.
        </strong><br>Om en exakt evenemangsplats inte finns på listan, välj då närmaste gatuadress och skriv 
        platsens namn eller ankomst instruktioner i fältet för tilläggsuppgifter.""",

        'en': """The event can be virtual, physical or both.
        <br><strong>If the event is virtual on the Internet, select Virtual event as the location and enter a URL. 
        You can enter details about the exact location, for example conference room name 
        or instruction to find an entrance.</strong><br>
        If you can't find the exact venue, then choose the nearest street address and enter the venue name 
        or arrival instructions in the additional information field."""
    },

    'location_mobile': {
        'fi': 'Paikan valinnan ohjeet',
        'sv': 'Anvisningen om att välja plats',
        'en': 'Instructions for selecting a location'
    }

}

@register_importer
class HelptextsImporter(Importer):
    # Importer class dependant attributes:
    name = 'helptexts'
    supported_languages = ('fi', 'sv', 'en')

    # Extra options.
    ignore_setup = True
    ignore_prerequisites = True

    def _get_data(self) -> None:
        for k, v in data.items():
            print(k, v)

    def _save(self) -> None:

        self._get_data()
        #try:
        #    sidefield_obj = Sidefield.objects.get(id=1)
        #except Sidefield.DoesNotExist:
        #    sidefield_obj = Sidefield()
        #    sidefield_obj.type_id = 1
        #    sidefield_obj.location_sidefield_fi = 'testtt'
        #    sidefield_obj.save()
        #    proc_time_frmt('Saved.')

    def __init__(self, options):
        proc_time_frmt('Initial')
        self._save()
        proc_time_frmt('Importer')
