# -*- coding: utf-8 -*-

# Dependencies.

# RDFLIB:
import rdflib
from rdflib import RDF, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS

# Logging:
import time
import logging
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext

# Django:
from django_orghierarchy.models import Organization
from django_orghierarchy.models import OrganizationClass
from events.models import DataSource, BaseModel

# Importer specific:
from .base import Importer, register_importer

# Type checking:
from typing import TYPE_CHECKING, Any

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


def tsl() -> dict:

    # These are custom with multilang support.
    # Prefix & ID are hardcoded as visual cues for mapping the management commands.
    hobby_content_target = {
        # Hobby content target:
        'tsl:p1': {'fi': 'Ajanvietepelit', 'sv': 'Underhållningsspel', 'en': 'Recreational games'},
        'tsl:p2': {'fi': 'Eläimet', 'sv': 'Djur', 'en': 'Animals'},
        'tsl:p3': {'fi': 'Kielet', 'sv': 'Språk', 'en': 'Languages'},
        'tsl:p4': {'fi': 'Kirjallisuus ja sanataide', 'sv': 'Litteratur och ordkonst', 'en': 'Literature and word art'},
        'tsl:p5': {'fi': 'Kuvataide ja media', 'sv': 'Bildkonst och media', 'en': 'Visual arts and media'},
        'tsl:p6': {'fi': 'Kädentaidot', 'sv': 'Hantverksskicklighet', 'en': 'Craftsmanship'},
        'tsl:p7': {'fi': 'Liikunta ja urheilu', 'sv': 'Motion och sport', 'en': 'Exercise and sports'},
        'tsl:p8': {'fi': 'Luonto', 'sv': 'Natur', 'en': 'Nature'},
        'tsl:p9': {'fi': 'Musiikki', 'sv': 'Musik', 'en': 'Music'},
        'tsl:p10': {'fi': 'Ruoka ja juoma', 'sv': 'Mat och dryck', 'en': 'Food and beverage'},
        'tsl:p11': {'fi': 'Teatteri, tanssi ja sirkus', 'sv': 'Teater, dans och cirkus', 'en': 'Theater, dance and circus'},
        'tsl:p12': {'fi': 'Tiede ja tekniikka', 'sv': 'Vetenskap och teknologi', 'en': 'Science and technology'},
        'tsl:p13': {'fi': 'Yhteisöllisyys ja auttaminen', 'sv': 'Kommunalitet och hjälpandet', 'en': 'Communality and assistance'},
        'tsl:p14': {'fi': 'Muut', 'sv': 'Övriga', 'en': 'Other'},
    }

    hobby_target_audience = {
        # Hobby target audience:
        'tsl:p15': {'fi': 'Maahanmuuttaneet', 'sv': 'Immigrerade', 'en': 'Immigrated'},
        'tsl:p16': {'fi': 'Toimintarajoitteiset', 'sv': 'Funktionshindrade', 'en': 'Functional limitations'},
        'tsl:p17': {'fi': 'Vauvat ja taaperot', 'sv': 'Spädbarn och småbarn', 'en': 'Babies and toddlers'},
        'tsl:p18': {'fi': 'Lapset ja lapsiperheet', 'sv': 'Barn och barnfamiljer', 'en': 'Children and families with children'},
        'tsl:p19': {'fi': 'Nuoret', 'sv': 'Ungdomar', 'en': 'Adolescents'},
        'tsl:p20': {'fi': 'Nuoret aikuiset', 'sv': 'Unga vuxna', 'en': 'Young adults'},
        'tsl:p21': {'fi': 'Aikuiset', 'sv': 'Vuxna', 'en': 'Adults'},
        'tsl:p22': {'fi': 'Ikääntyneet', 'sv': 'Äldre', 'en': 'Elderly'},
    }

    event_target_audience = {
        # Event target audience:
        'tsl:p23': {'fi': 'Opiskelijat', 'sv': 'Studenter', 'en': 'Students'},
        'tsl:p24': {'fi': 'Matkailijat', 'sv': 'Resenärer', 'en': 'Travelers'},
        'tsl:p25': {'fi': 'Työnhakijat', 'sv': 'Arbetssökande', 'en': 'Job seekers'},
        'tsl:p26': {'fi': 'Yrittäjät', 'sv': 'Företagare', 'en': 'Entrepreneurs'},
        'tsl:p27': {'fi': 'Harrastajat', 'sv': 'Hobbyister', 'en': 'Hobbyists'},
    }

    event_content_based = {
        # Event content based:
        'tsl:p28': {'fi': 'Kuvataide', 'sv': 'Bildkonst', 'en': 'Visual art'},
        'tsl:p29': {'fi': 'Tanssi', 'sv': 'Dans', 'en': 'Dancing'},
        'tsl:p30': {'fi': 'Elokuva', 'sv': 'Film', 'en': 'Movie'},
        'tsl:p31': {'fi': 'Käsityöt', 'sv': 'Hantverk', 'en': 'Handicraft'},
        'tsl:p32': {'fi': 'Terveys ja hyvinvointi', 'sv': 'Hälsa och välbefinnande', 'en': 'Health and welfare'},
        'tsl:p33': {'fi': 'Luonto ja kulttuuriympäristö', 'sv': 'Natur och kulturmiljö', 'en': 'Nature and cultural environment'},
        'tsl:p34': {'fi': 'Uskonto ja hengellisyys', 'sv': 'Religion och andlighet', 'en': 'Religion and spirituality'},
        'tsl:p35': {'fi': 'Yritystoiminta ja työelämä', 'sv': 'Företagsverksamhet och arbetsliv', 'en': 'Business and worklife'},
        'tsl:p36': {'fi': 'Yhteiskunta', 'sv': 'Samhället', 'en': 'Society'},
        'tsl:p36': {'fi': 'Historia', 'sv': 'Historia', 'en': 'History'},
    }

    event_type_based = {
        # Event type based:
        'tsl:p37': {'fi': 'Festivaalit', 'sv': 'Festivaler', 'en': 'Festivals'},
        'tsl:p38': {'fi': 'Kaupunkitapahtumat', 'sv': 'Stadsevenemang', 'en': 'City events'},
        'tsl:p39': {'fi': 'Keskustelutilaisuudet', 'sv': 'Diskussionshändelser', 'en': 'Discussion events'},
        'tsl:p40': {'fi': 'Kilpailut', 'sv': 'Tävlingar', 'en': 'Competitions'},
        'tsl:p41': {'fi': 'Kokoukset, seminaarit ja kongressit', 'sv': 'Möten, seminarier och kongresser', 'en': 'Meetings, seminars and congresses'},
        'tsl:p42': {'fi': 'Konsertit', 'sv': 'Konserter', 'en': 'Concerts'},
        'tsl:p43': {'fi': 'Koulutustapahtumat', 'sv': 'Utbildningsevenemang', 'en': 'Educational events'},
        'tsl:p44': {'fi': 'Leirit', 'sv': 'Läger', 'en': 'Camps'},
        'tsl:p45': {'fi': 'Luennot', 'sv': '', 'en': ''},
        'tsl:p46': {'fi': 'Markkinat', 'sv': '', 'en': ''},
        'tsl:p47': {'fi': 'Messut', 'sv': '', 'en': ''},
        'tsl:p48': {'fi': 'Myyjäiset', 'sv': '', 'en': ''},
        'tsl:p49': {'fi': 'Näyttelyt', 'sv': '', 'en': ''},
        'tsl:p50': {'fi': 'Opastukset', 'sv': '', 'en': ''},
        'tsl:p51': {'fi': 'Retket', 'sv': '', 'en': ''},
        'tsl:p52': {'fi': 'Työpajat', 'sv': 'Verkstad', 'en': 'Workshop'},
        'tsl:p53': {'fi': 'Verkostoitumistapahtumat', 'sv': '', 'en': ''},
        # Word "Muu" is already existing as "Muut" ?
    }

    # Unfinished.


@register_importer
class TslImporter(Importer):
    # Importer class dependant attributes:
    name = "tsl"  # Command calling name.
    supported_languages = ['fi', 'sv', 'en']  # Base file requirement.

    def iterator(self: 'events.importer.tsl.TslImporter', data: dict, key: str, query: Any, obj_model: tuple, attr_map: tuple) -> None:
        # Main class data logic. Create DB objects & set class attributes.
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

    # Setup our class attributes & Add to DB.
    def setup(self) -> None:
        # Data mapped by models order:
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
        mapped = list(map(lambda f, fto, mm, atm: [f, fto, self.data['model_maps'][mm], self.data['attr_maps'][atm]],
                      self.data['funcargs']['terms'], self.data['funcargs']['termobjs'], self.data['model_maps'], self.data['attr_maps']))
        for args in mapped:
            self.iterator(
                data=self.data, key=args[0], query=args[1], obj_model=args[2], attr_map=args[3])
        logger.info(
            "#1: Setup finished in: %s. Fetching JUPO turtle graph file..." % time.process_time())

        self.handle()

    def handle()
    logger.info("Gather TSL keywords...")
    self.keywords = tsl()
