
#Dependencies
import logging
import requests
import requests_cache
import re 
import dateutil.parser
import time
import pytz
import bleach
from datetime import datetime, timedelta
from django.utils.html import strip_tags 
from events.models import Event, Keyword, DataSource, Place, License, Image, Language, EventLink
from django_orghierarchy.models import Organization, OrganizationClass
from pytz import timezone
from django.conf import settings
from .util import clean_text
from .sync import ModelSyncher
from .base import Importer, register_importer, recur_dict
from .yso import KEYWORDS_TO_ADD_TO_AUDIENCE
from os import mkdir
from os.path import abspath, join, dirname, exists, basename, splitext
from copy import copy

if not exists(join(dirname(__file__), 'logs')):
    mkdir(join(dirname(__file__), 'logs'))


__setattr__ = setattr


logger = logging.getLogger(__name__) # Per module logger


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


virtualPublic = "virtual:public"
drupalUrl = 'https://kalenteri.turku.fi/admin/event-exports/json_beta'
keywordsList = []


TURKU_KEYWORD_IDS = {
    'Festivaalit': 'yso:p1304',  # -> Festivaalit
    'Konferenssit ja kokoukset': 'yso:p38203',  # -> Konferenssit (ja kokoukset)
    'Messut': 'yso:p4892', # -> Messut
    'Myyjäiset': 'yso:p9376',  # -> Myyjäiset
    'Musiikki': 'yso:p1808',  # -> Musiikki
    'Museot': 'yso:p4934',  # -> Museot
    'Näyttelyt': 'yso:p5121',  # -> Näyttelyt
    'Luennot': 'yso:p15875', # -> Luennot
    'Osallisuus': 'yso:p5164',  # -> Osallisuus
    'Monikulttuurisuus': 'yso:p10647',  # -> Monikulttuurisuus
    'Retket': 'yso:p25261', # -> Retket
    'Risteilyt': 'yso:p1917', # -> Risteilyt
    'Matkat': 'yso:p366',  # -> Matkat
    'Matkailu': 'yso:p3917', # -> Matkailu
    'Opastus': 'yso:p2149',  # -> Opastus
    'Teatteritaide': 'yso:p2625', # -> Teatteritaide
    'Muu esittävä taide': 'yso:p2850', # -> Muu esittävä taide
    'Urheilu': 'yso:p965', # -> Urheilu
    'Kirjallisuus': 'yso:p8113', # -> Kirjallisuus
    'Tapahtumat ja toiminnat': 'yso:p15238', # -> Tapahtumat ja toiminnat
    'Ruoka': 'yso:p3670',  # -> Ruoka
    'Tanssi': 'yso:p1278',  # -> Tanssi
    'Työpajat': 'yso:p19245',  # -> Työpajat
    'Ulkoilu': 'yso:p2771',  # -> Ulkoilu
    'Etäosallistuminen': 'yso:p26626', # -> Etäosallistuminen
}


TURKU_AUDIENCES_KEYWORD_IDS = {
    'Aikuiset': 'yso:p5590', # -> Aikuiset
    'Lapsiperheet': 'yso:p13050', # -> Lapsiperheet
    'Maahanmuttajat': 'yso:p6165', # -> Maahanmuuttujat
    'Matkailijat': 'yso:p16596', # -> Matkailijat
    'Nuoret': 'yso:p11617', # -> Nuoret
    'Seniorit': 'yso:p2433', # -> Seniorit
    'Työnhakijat': 'yso:p9607', # -> Työnhakijat
    'Vammaiset': 'yso:p7179', # -> Vammaiset
    'Vauvat': 'yso:p15937', # -> Vauvat
    'Viranomaiset': 'yso:p6946', # -> Viranomaiset
    'Järjestöt': 'yso:p1393', # -> järjestöt  
    'Yrittäjät': 'yso:p1178', # -> Yrittäjät  
}


TURKU_DRUPAL_CATEGORY_EN_YSOID = {
    'Exhibits': 'yso:p5121', # -> Utställningar # -> Näyttelyt 
    'Festival and major events': 'yso:p1304', # -> Festivaler #Festivaalit ja suurtapahtumat (http://www.yso.fi/onto/yso/p1304)
    'Meetings and congress ': 'yso:p7500', # -> Möten, symposier (sv), kongresser (sv), sammanträden (sv) # -> Kokoukset (http://www.yso.fi/onto/yso/p38203)
    'Trade fair and fair': 'yso:p4892', # -> Messut , mässor (evenemang), (messut: http://www.yso.fi/onto/yso/p4892; myyjäiset : http://www.yso.fi/onto/yso/p9376)
    'Music': 'yso:p1808', # -> Musiikki, musik, http://www.yso.fi/onto/yso/p1808
    'Museum': 'yso:p4934', # -> Museo,  museum (en), museer (sv) (yso museot: http://www.yso.fi/onto/yso/p4934)
    'Lectures':'yso:p15875', # -> Luennot,föreläsningar (sv), http://www.yso.fi/onto/yso/p15875
    'Participation':'yso:p5164', # -> Osallisuus,delaktighet (sv), http://www.yso.fi/onto/yso/p5164
    'Multiculturalism':'yso:p10647', # -> Monikulttuurisuus,multikulturalism, http://www.yso.fi/onto/yso/p10647
    'Trips,cruises and tours':'yso:p3917', # -> Matkailu, turism (sv)
    'Guided tours and sightseeing tours':'yso:p2149', # -> guidning (sv),Opastukset: http://www.yso.fi/onto/yso/p2149; 
    'Theatre and other performance art':'yso:p2850', # -> scenkonst (sv),Esittävä taide: http://www.yso.fi/onto/yso/p2850;  
    'Sports':'yso:p965', # -> Urheilu,idrott, http://www.yso.fi/onto/yso/p965
    'Christmas':'yso:p419', # -> Joulu,julen, http://www.yso.fi/onto/yso/p419	
    'Literature':'yso:p8113', # -> Kirjallisuus, litteratur (sv), http://www.yso.fi/onto/yso/p8113
    'Others':'yso:p10727', # -> Ulkopelit,(-ei ysoa, ei kategoriaa)	
}


TURKU_DRUPAL_AUDIENCES_KEYWORD_EN_YSOID = {
    'Adults': 'yso:p5590',
    'Child families': 'yso:p13050',
    'Immigrants': 'yso:p6165',
    'Travellers': 'yso:p16596',
    'Youth': 'yso:p11617',
    'Elderly': 'yso:p2433',
    'Jobseekers': 'yso:p9607',
    'Disabled': 'yso:p7179',
    'Infants and toddlers': 'yso:p15937',
    'Authorities': 'yso:p6946',
    'Associations and communities': 'yso:p1393',
    'Entrepreneurs': 'yso:p1178',
}


languagesList =  ['fi', 'sv' , 'en']
CITY_LIST = ['turku', 'naantali', 'raisio', 'nousiainen', 'mynämäki', 'masku', 'aura', 'marttila', 'kaarina', 'lieto', 'paimio', 'sauvo']
LOCAL_TZ = timezone('Europe/Helsinki')

def set_deleted_false(obj):
    obj.deleted = False
    obj.save(update_fields=['deleted'])
    return True


#It is easier to keep track of and access Events if we store them into lists.
umbrellaEvents = [] # Kattotapahtumat (Umbrella)
singleEvents = [] # Yksittäiset tapahtumat (Single events)
recurringEvents = [] # Sarjatapahtumat (Äidit) (SERIES)
childEvents = [] # Sarjatapahtuman lapset (Child)


# Logic of the program:

# Umbrellas are imported only if they contain SOMETHING, it can be anything.
# Umbrellas are always 'top level' meaning there SHOULDN'T be anything. For example it is prohibited -
# to make an Umbrella event that contains another Umbrella event.

# Single events CAN have an Umbrella or can be underneath an Umbrella event. They are not within Series because -
# Single events don't contain any events because only 'Series' and 'Umbrellas' contain sub events.

# Recurring events are mother events, meaning they are of the type: "Series".
# Recurring events are not imported at all if they DON'T contain anything.
# Recurring events don't necessarily need an Umbrella event.

# Child events are events within Series. Child events CAN'T contain events and they can't be Umbrella events.
# Child events that don't find their mother event are not imported.

class APIBrokenError(Exception):
    pass


@register_importer
class TurkuOriginalImporter(Importer):
    name = curFile
    supported_languages = languagesList #LANGUAGES
    languages_to_detect = []
    current_tick_index = 0
    kwcache = {}

    def setup(self):
        self.languages_to_detect = [lang[0].replace('-', '_') for lang in settings.LANGUAGES
                                    if lang[0] not in self.supported_languages]
        ds_args = dict(id='turku')
        defaults = dict(name='Kuntakohtainen data Turun Kaupunki')
        self.data_source, _ = DataSource.objects.update_or_create(
            defaults=defaults, **ds_args)
        self.tpr_data_source = DataSource.objects.get(id='tpr')
        self.org_data_source = DataSource.objects.get(id='org')
        self.system_data_source = DataSource.objects.get(id=settings.SYSTEM_DATA_SOURCE_ID)

        ds_args = dict(origin_id='3', data_source=self.org_data_source)
        defaults = dict(name='Kunta')
        self.organizationclass, _ =  OrganizationClass.objects.update_or_create(defaults=defaults, **ds_args)

        org_args = dict(origin_id='853', data_source=self.data_source, classification_id="org:3")
        defaults = dict(name='Turun kaupunki')
        self.organization, _ = Organization.objects.update_or_create(defaults=defaults, **org_args)

        ds_args4 = dict(id='virtual', user_editable=True)
        defaults4 = dict(name='Virtuaalitapahtumat')
        self.data_source_virtual, _ = DataSource.objects.update_or_create(defaults=defaults4, **ds_args4)


        org_args4 = dict(origin_id='3000', data_source=self.data_source_virtual, classification_id="org:14")
        defaults4 = dict(name='Virtuaalitapahtumat')        
        self.organization_virtual, _ = Organization.objects.update_or_create(defaults=defaults4, **org_args4)

        defaults5 = dict(data_source=self.data_source_virtual,
                        publisher=self.organization_virtual,
                        name='Virtuaalitapahtuma',
                        name_fi='Virtuaalitapahtuma',
                        name_sv='Virtuell evenemang',
                        name_en='Virtual event',
                        description='Toistaiseksi kaikki virtuaalitapahtumat merkitään tähän paikkatietoon.',)
        self.internet_location, _ = Place.objects.update_or_create(id="virtual:public", defaults=defaults5)

        try:
            self.event_only_license = License.objects.get(id='event_only')
        except License.DoesNotExist:
            self.event_only_license = None

        try:
            self.cc_by_license = License.objects.get(id='cc_by')
        except License.DoesNotExist:
            self.cc_by_license = None

        try:
            yso_data_source = DataSource.objects.get(id='yso')
        except DataSource.DoesNotExist:
            yso_data_source = None

        if yso_data_source: # -> Build a cached list of YSO keywords
            cat_id_set = set()
            for yso_val in TURKU_KEYWORD_IDS.values():
                if isinstance(yso_val, tuple):
                    for t_v in yso_val:
                        cat_id_set.add(t_v)
                else:
                    cat_id_set.add(yso_val)

            KEYWORD_LIST = Keyword.objects.filter(data_source=yso_data_source).\
                filter(id__in=cat_id_set)
            self.yso_by_id = {p.id: p for p in KEYWORD_LIST}
        else:
            self.yso_by_id = {}

        if self.options['cached']:
            requests_cache.install_cache('turku')
            self.cache = requests_cache.get_cache()
        else:
            self.cache = None



    @staticmethod
    def _get_eventTurku(event_el): # -> This reads our JSON dump and fills the eventTurku with our data
        eventTurku = recur_dict()
        eventTurku = event_el
        return eventTurku

    def _cache_super_event_id(self, sourceEventSuperId):
        superid = (self.data_source.name + ':' + sourceEventSuperId)
        one_super_event = Event.objects.get(id=superid)
        return one_super_event

    def dt_parse(self, dt_str):
        """Convert a string to UTC datetime"""
        # Times are in UTC+02:00 timezone
        return LOCAL_TZ.localize(
                dateutil.parser.parse(dt_str),
                is_dst=None).astimezone(pytz.utc)

    def timeToTimestamp(self, origTime):
        timestamp = time.mktime(time.strptime(origTime, '%d.%m.%Y %H.%M'))
        dt_object = datetime.fromtimestamp(timestamp)
        return str(dt_object)

    def with_value(self, data : dict, value : object, default : object):
        item = data.get(value, default)
        if not item:
            return default
        return item

    def _import_event(self, lang, event_el, events, event_image_url, type_of_event):
        eventTurku = self._get_eventTurku(event_el)

        start_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['start_date'])))
        end_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['end_date'])))

        # Import only at most one year old events
        if end_time < datetime.now().replace(tzinfo=LOCAL_TZ) - timedelta(days=365):
            return {'start_time': start_time, 'end_time': end_time}

        # -> We don't want to import hobbies at this time.
        if not bool(int(eventTurku['is_hobby'])): 
            eid = int(eventTurku['drupal_nid'])
            eventItem = events[eid]
            eventItem['id'] = '%s:%s' % (self.data_source.id, eid)
            eventItem['origin_id'] = eid
            eventItem['data_source'] = self.data_source
            eventItem['publisher'] = self.organization
            eventItem['end_time'] = end_time

            event_categories = eventItem.get('event_categories', set())

            if event_categories:
                pass
            else:
                logger.info("No event_categories found for current event. Skipping...")

            ok_tags = ('u', 'b', 'h2', 'h3', 'em', 'ul', 'li', 'strong', 'br', 'p', 'a')

            eventItem['name'] = {"fi": eventTurku['title_fi'], "sv": eventTurku['title_sv'], "en": eventTurku['title_en']}

            eventItem['description'] = {
                "fi": bleach.clean(self.with_value(eventTurku, 'description_markup_fi', ''),   tags=[],   strip=True),
                "sv": bleach.clean(self.with_value(eventTurku, 'description_markup_sv', ''),   tags=[],   strip=True),
                "en": bleach.clean(self.with_value(eventTurku, 'description_markup_en', ''),   tags=[],   strip=True)
            }

            eventItem['short_description'] = {
                "fi": bleach.clean(self.with_value(eventTurku, 'lead_paragraph_markup_fi', ''),   tags=[],   strip=True),
                "sv": bleach.clean(self.with_value(eventTurku, 'lead_paragraph_markup_sv', ''),   tags=[],   strip=True),
                "en": bleach.clean(self.with_value(eventTurku, 'lead_paragraph_markup_en', ''),   tags=[],   strip=True)
            }

            eventItem['provider'] = {"fi": 'Turku', "sv": 'Åbo', "en": 'Turku'}

            location_extra_info = ''

            if self.with_value(eventTurku, 'address_extension', ''):
                location_extra_info += '%s, ' % bleach.clean(self.with_value(eventTurku, 'address_extension', ''), tags=[], strip=True)
            if self.with_value(eventTurku, 'city_district', ''):
                location_extra_info += '%s, ' % bleach.clean(self.with_value(eventTurku, 'city_district', ''), tags=[], strip=True)
            if self.with_value(eventTurku, 'place', ''):
                location_extra_info += '%s' % bleach.clean(self.with_value(eventTurku, 'place', ''), tags=[], strip=True)


            if type_of_event == "recurring":
                eventItem['super_event_type'] = Event.SuperEventType.RECURRING


            event_image_ext_url = ''
            image_license = ''
            event_image_license = self.event_only_license

            #NOTE! Events image is not usable in Helmet must use this Lippupiste.py way to do it         
            if event_image_url:
                event_image_ext_url = event_image_url

                #event_image_license 1 or 2 (1 is 'event_only' and 2 is 'cc_by' in Linked Events) NOTE! CHECK VALUES IN DRUPAL!
                if eventTurku['event_image_license']:
                    image_license = eventTurku['event_image_license']
                    if image_license == '1':
                        event_image_license = self.event_only_license
                    elif image_license == '2':
                        event_image_license = self.cc_by_license

                eventItem['images'] = [{
                    'url': event_image_ext_url,
                    'license': event_image_license,
                    }]

            def set_attr(field_name, val):
                if field_name in eventItem:
                    if eventItem[field_name] != val:
                        logger.warning('Event %s: %s mismatch (%s vs. %s)' %
                                    (eid, field_name, eventItem[field_name], val))
                        return
                eventItem[field_name] = val

            eventItem['date_published'] = self.dt_parse(self.timeToTimestamp(str(eventTurku['start_date'])))
            
            set_attr('start_time', self.dt_parse(self.timeToTimestamp(str(eventTurku['start_date']))))
            set_attr('end_time', self.dt_parse(self.timeToTimestamp(str(eventTurku['end_date']))))


            event_in_language = eventItem.get('in_language', set())
            try:
                eventLang = Language.objects.get(id='fi')
            except:
                logger.info('Language (fi) not found.')
            if eventLang:
                event_in_language.add(self.languages[eventLang.id])

            eventItem['in_language'] = event_in_language

            event_keywords = eventItem.get('keywords', set())
            event_audience = eventItem.get('audience', set())

            if eventTurku['event_categories'] != None:
                eventTurku['event_categories'] =eventTurku['event_categories'] + ','
                categories = eventTurku['event_categories'].split(',')
                for name in categories:
                    if name in TURKU_DRUPAL_CATEGORY_EN_YSOID.keys():
                        ysoId = TURKU_DRUPAL_CATEGORY_EN_YSOID[name]
                        event_keywords.add(Keyword.objects.get(id= ysoId))

            if eventTurku['keywords'] != None:
                eventTurku['keywords'] =eventTurku['keywords'] + ','
                keywords = eventTurku['keywords'].split(',')
                for name in keywords:
                    if name not in TURKU_DRUPAL_CATEGORY_EN_YSOID.keys():
                        try:                
                            event_keywords.add(Keyword.objects.get(name = name))
                        except:
                            print('Warning!' + ' keywords not found:' + name)
                            logger.warning('Moderator should add the following keywords ' + name)    
                            pass

            eventItem['keywords'] = event_keywords

            if eventTurku['target_audience'] != None:
                eventTurku['target_audience'] =eventTurku['target_audience'] + ','
                audience = eventTurku['target_audience'].split(',')
                for name in audience:
                    if name in TURKU_DRUPAL_AUDIENCES_KEYWORD_EN_YSOID.keys():
                        ysoId = TURKU_DRUPAL_AUDIENCES_KEYWORD_EN_YSOID[name]
                        event_audience.add(Keyword.objects.get(id= ysoId))

            eventItem['audience'] = event_audience

            tprNo = ''

            if eventTurku.get('event_categories', None):
                node_type = eventTurku['event_categories'][0]
                if node_type == 'Virtual events':
                    eventItem ['location']['id'] = "virtual:public"
                elif str(eventTurku['palvelukanava_code']):
                    tprNo = str(eventTurku['palvelukanava_code'])
                    if tprNo == '10123':    tprNo = '148'
                    elif tprNo == '10132':  return
                    elif tprNo == '10174':  return
                    elif tprNo == '10129':  return

                    eventItem ['location']['id'] = ('tpr:' + tprNo)
                else:
                    def numeric(string):
                        from hashlib import md5
                        h = md5()
                        h.update(string.encode())
                        return str(int(h.hexdigest(), 16))[0:6]
                    #This json address data is made by hand and it could be anything but a normal format;
                    # 'Piispankatu 4, Turku' is modified to Linked Events Place Id mode like
                    # 'osoite:piispankatu_4_turku'
                    if eventTurku['address']:
                        import re
                        event_address = copy(eventTurku['address'])
                        event_address_name = copy(eventTurku['address'])
                        event_name = ""
                        event_postal_code = None
                        regex = re.search(r'\d{4,6}', event_address_name, re.IGNORECASE)
                        if regex:
                            event_postal_code = regex.group(0)
                        if event_address_name.startswith('('):

                            regex = re.search(r'\((.*?)\)\\?(.*|[a-z]|[0-9])', event_address, re.IGNORECASE) # Match: (str, str) str
                            event_name = '%s' % regex.group(1)

                            try:
                                _regex = re.search(r'(?<=\))[^\]][^,]+', regex.group(0), re.IGNORECASE)
                                event_address_name = _regex.group(0).strip().capitalize()
                            except:
                                _regex = re.search(r'(?<=\))[^\]][^,]+', regex.group(1), re.IGNORECASE)
                                event_address_name = _regex.group(0).strip().capitalize()

                        else:
                            _regex = re.search(r'(?<=)[^\]][^,]+', event_address_name, re.IGNORECASE)
                            event_name = _regex.group(0).strip().capitalize()
                        
                        city = ""
                        for _city in CITY_LIST:
                            if len(event_address.split(',')) >= 2:
                                if event_address.split(',')[1].lower().strip() == _city.lower():
                                    city = _city
                                    break


                        addr = 'osoite:%s' % (''.join(
                                event_address.replace(' ','_')      \
                                .split(','))                        \
                                .strip()                            \
                                .lower()                            \
                                .replace('k.','katu'))

                        if city and not addr.endswith(city):
                            addr += '_%s' % city.lower()
                        elif city and addr.endswith(city):
                            ...
                        elif not city and not addr.endswith('_turku'):
                            addr += '_turku'

                        origin_id = numeric(addr)
                        tpr = '%s:%s' % (str(eventItem.get('data_source')), origin_id)  # Mimic tpr
                        try:
                            place_id = Place.objects.get(id=tpr)
                        except:
                            def build_place_information(data : dict, translated=[]) -> Place:
                                p = Place()
                                for k in data:
                                    __setattr__(p, k, data[k])
                                    if k in translated:
                                        __setattr__(p, '%s_fi' % k, data[k])
                                        __setattr__(p, '%s_en' % k, data[k])
                                        __setattr__(p, '%s_sv' % k, data[k])
                                return p

                            place = \
                                build_place_information({
                                    'name': event_name,
                                    'street_address': event_address_name,
                                    'id': tpr,
                                    'origin_id': origin_id,
                                    'data_source': eventItem.get('data_source'),
                                    'publisher': eventItem.get('publisher'),
                                    'postal_code': event_postal_code
                                }, translated=[
                                    'name', 
                                    'street_address'
                                    ]
                                )
                            place.save()
                        eventItem ['location']['id'] = tpr

            '''
            #NOTE! Tarkistetaan heti aluksi onko tapahtuma äitielementti, sillä aluksi ei lueta lapsielemettejä ollenkaan sisää
            # vasta näiden jälkeen käydäään lapset läpi ja vain täydennetään niiden tietoja drupal-lähteestä, 
            # jos eroja äititapahtumaan  
            
            #This is the super event match foreign key
            if eventTurku['drupal_nid_super']:
                eventItem['super_event_id'] = eventTurku['drupal_nid_super']
                del eventTurku['drupal_nid_super']
            '''

            # Add a default offer
            free_offer = {
                'is_free': True,
                'price': None,
                'description': None,
                'info_url': None,
            }

            eventOffer_is_free = bool(int(eventTurku['free_event']))
            #Fill event_offer table information if events is not free price event
            if not eventOffer_is_free:
                if eventTurku['event_price']: 
                    ok_tags = ('u', 'b', 'h2', 'h3', 'em', 'ul', 'li', 'strong', 'br', 'p', 'a')
                    price = str(eventTurku['event_price'])                 
                    price = bleach.clean(price, tags= ok_tags, strip=True)
                    free_offer_price = clean_text(price, True)
                else: 
                    free_offer_price = 'No price'

                if str(eventTurku['buy_tickets_url']): 
                    free_offer_buy_tickets = eventTurku['buy_tickets_url'] 
                else:
                    free_offer_buy_tickets = '' 
            
                free_offer['is_free'] = False
                free_offer['price'] = {'fi': free_offer_price}
                free_offer['description'] = ''
                free_offer['info_url'] =  {'fi': free_offer_buy_tickets}

            eventItem['offers'] = [free_offer]
            return eventItem

    def _recur_fetch_paginated_url(self, url, lang, events):
        maxTries = 5
        for tryNumber in range(0, maxTries):            
            response = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})
            if response.status_code != 200:
                logger.warning("Turku Drupal orig API reported HTTP %d" % response.status_code)
            if self.cache:
                self.cache.delete_url(url)
                continue
            try:
                rootDoc = response.json()
            except ValueError:
                logger.warning("Turku Drupal orig API returned invalid JSON (try {} of {})".format(tryNumber + 1, maxTries))
                if self.cache:
                    self.cache.delete_url(url)
                    continue
            break
        else:
            logger.error("Turku Drupal orig API broken again, giving up")
            raise APIBrokenError()

        jsonRootEvent = rootDoc['events']

        earliest_end_time = None
        event_image_url = None

        # -> Loops through each event.
        for json_event in jsonRootEvent:
            currentEvent = json_event['event']


            # -> JSON exceptions
            if currentEvent['event_image_ext_url']:
                event_image_url = currentEvent['event_image_ext_url']['src']
            else:
                event_image_url = ""

            logger.info(currentEvent)
            
            # -> We start by trying to find all Event series.
            if currentEvent['event_type'] == "Event series":
                type_of_event = "recurring"
                logger.info("Importing Event Series...")
                event = self._import_event(lang, currentEvent, events, event_image_url, type_of_event)

            elif currentEvent['event_type'] == "Recurring event (in series)":
                type_of_event = "child"
                logger.info("Importing Child Event...")
                event = self._import_event(lang, currentEvent, events, event_image_url, type_of_event)

            elif currentEvent['event_type'] == "Single event":
                type_of_event = "single"
                logger.info("Importing Single Event...")
                event = self._import_event(lang, currentEvent, events, event_image_url, type_of_event)
            else:
                logger.info("Event had no event_type and therefore wasn't imported.")
        now = datetime.now().replace(tzinfo=LOCAL_TZ)


    def _import_child_event(self, lang, eventTurku):
        eventMother = None
        eventImage = None
        eventRecurring = None

        sourceEventSuperId = eventTurku['drupal_nid_super']
        sourceEventId = eventTurku['drupal_nid']
        #sourceEventImageUrl = eventTurku['event_image_ext_url']['src']

        if sourceEventSuperId:
            logger.info(str(sourceEventSuperId))

        if sourceEventId:
            logger.info(str(sourceEventId))

        eventFacebook = eventTurku['facebook_url']
        eventTwitter = eventTurku['twitter_url']

        if eventFacebook:
            logger.info(eventFacebook)
        if eventTwitter:
            logger.info(eventTwitter)

        '''
        #sourceEventLang = 'fi'
        #sourceEventLinkWeb = eventTurku['website_url']
        #sourceEventLinkFace = eventTurku['facebook_url']
        #sourceEventLinkTwit = eventTurku['twitter_url']
        '''

        superId = (self.data_source.id + ':' + sourceEventSuperId)
        sourceId = (self.data_source.id + ':' + sourceEventId)

        try:
            eventMother = Event.objects.get(id=superId)
        except:
            return

        try:
            eventRecurring = Event.objects.get(super_event_id = eventMother.id, super_event_type = Event.SuperEventType.RECURRING)
        except:
            pass

        if eventRecurring:
            eventMother = eventRecurring

        usableSuperEventId = eventMother.id

        if not eventMother.deleted:
            if eventMother.super_event_type == Event.SuperEventType.UMBRELLA:

                temp = copy(eventMother)
                temp.id = eventMother.id
                temp.super_event_type = Event.SuperEventType.RECURRING
                temp.start_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['start_date'])))
                temp.end_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['end_date'])))
                temp.super_event_id = usableSuperEventId
                temp.origin_id = str(temp.id).split(':')[1]
                temp.save(force_insert=True)

            elif eventMother.super_event_type == Event.SuperEventType.RECURRING:

                Event.objects.update_or_create(
                    id = eventMother.id,
                    defaults = {
                    'date_published' : datetime.now(),
                    'provider': 'Turku',
                    'provider_fi': 'Turku',
                    'provider_sv': 'Åbo',
                    'provider_en': 'Turku',
                    'deleted': False} 
                    )
                temp = copy(eventMother)
                temp.id = sourceId
                temp.super_event_type = None
                temp.start_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['start_date'])))
                temp.end_time = self.dt_parse(self.timeToTimestamp(str(eventTurku['end_date'])))
                temp.super_event_id = usableSuperEventId
                temp.origin_id = str(temp.id).split(':')[1]
                temp.save()

    def saveChildElement(self, url, lang):
        max_tries = 5
        for try_number in range(0, max_tries):
            response = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})
            if response.status_code != 200:
                logger.warning("tku Drupal orig API reported HTTP %d" % response.status_code)
                time.sleep(2)
            if self.cache:
                self.cache.delete_url(url)
                continue
            try:
                root_doc = response.json()
            except ValueError:
                logger.warning("tku Drupal orig API returned invalid JSON (try {} of {})".format(try_number + 1, max_tries))
                if self.cache:
                    self.cache.delete_url(url)
                    time.sleep(5)
                    continue
            break
        else:
            logger.error("Turku Drupal orig API broken again, giving up")
            raise APIBrokenError()

        json_root_event = root_doc['events']
        earliest_end_time = None
        eventImageUrl = None

        for json_event in json_root_event:
            json_event = json_event['event']
            eventTurku = self._get_eventTurku(json_event)

            if eventTurku['event_type'] == "Recurring event (in series)":
                logger.info("_import_child_event called.")
                motherFound = self._import_child_event(lang, eventTurku)
                #self.syncher.finish(force=self.options['force'])

        now = datetime.now().replace(tzinfo=LOCAL_TZ)



    # -> MAIN.
    def import_events(self):
        logger.info("Importing old Turku events...")
        events = recur_dict()
        url = drupalUrl
        lang = self.supported_languages

        try:
            self._recur_fetch_paginated_url(url, lang, events)
        except APIBrokenError:
            return

        event_list = sorted(events.values(), key=lambda x: x['end_time'])
        qs = Event.objects.filter(end_time__gte=datetime.now(), data_source='turku')
        self.syncher = ModelSyncher(qs, lambda obj: obj.origin_id, delete_func=set_deleted_false)

        for event in event_list:
            try:
                obj = self.save_event(event)
                self.syncher.mark(obj)
            except:
                ...

        self.syncher.finish(force=True)

        try:
            self.saveChildElement(url, lang)
        except APIBrokenError:
            return

        self.syncher.finish(force=True)
        logger.info("%d events processed" % len(events.values()))