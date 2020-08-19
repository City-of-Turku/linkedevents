#Documentation will be rewritten in the near future.
#Improved code integrated with previous code version + extra.
#08/08/2020


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
from events.models import Event, Keyword, DataSource, Place, License, Image, Language, EventLink, Offer
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


VIRTUAL_LOCATION_ID = "virtual:public"
TKUDRUPAL_BASE_URL = 'https://kalenteri.turku.fi/admin/event-exports/json_beta'
KEYWORD_LIST = []


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


LANGUAGES_TURKU_OLD =  ['fi', 'sv' , 'en']
CITY_LIST = ['turku', 'naantali', 'raisio', 'nousiainen', 'mynämäki', 'masku', 'aura', 'marttila', 'kaarina', 'lieto', 'paimio', 'sauvo']
LOCAL_TZ = timezone('Europe/Helsinki')
drupal_json_response = []
mothersList = []
childList = []

def set_deleted_false(obj):
    obj.deleted = False
    obj.save(update_fields=['deleted'])
    return True


class APIBrokenError(Exception):
    pass


@register_importer
class TurkuOriginalImporter(Importer):
    name = curFile
    supported_languages = LANGUAGES_TURKU_OLD #LANGUAGES
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
        defaults4 = dict(name='Virtuaalitapahtumat (ei paikkaa, vain URL)')
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
        self.internet_location, _ = Place.objects.update_or_create(id=VIRTUAL_LOCATION_ID, defaults=defaults5)

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
    def _get_eventTku(event_el): # -> This reads our JSON dump and fills the eventTku with our data
        eventTku = recur_dict()
        eventTku = event_el
        return eventTku


    def _cache_super_event_id(self, sourceEventSuperId):
        superid = (self.data_source.name + ':' + sourceEventSuperId)
        one_super_event = Event.objects.get(id=superid)
        return one_super_event


    def dt_parse(self, dt_str): 
        """Convert a string to UTC datetime""" # -> Times are in UTC+02:00 timezone
        return LOCAL_TZ.localize(
                dateutil.parser.parse(dt_str),
                is_dst=None).astimezone(pytz.utc)


    def timeToTimestamp(self, origTime):
        timestamp = time.mktime(time.strptime(origTime, '%d.%m.%Y %H.%M'))
        dt_object = datetime.fromtimestamp(timestamp)
        return str(dt_object)


    #def import_eventlink(self, typeSocial):
        #EventLink to be made. Probably not necessary as a function but rather as a loop.

    def with_value(self, data : dict, value : object, default : object):
        item = data.get(value, default)
        if not item:
            return default
        return item

    def _import_event(self, lang, event_el, events, event_image_url, eventType, mothersList, childList):
        eventTku = self._get_eventTku(event_el)
        start_time = self.dt_parse(self.timeToTimestamp(str(eventTku['start_date'])))
        end_time = self.dt_parse(self.timeToTimestamp(str(eventTku['end_date'])))

        # -> Import only at most one year old events.
        if end_time < datetime.now().replace(tzinfo=LOCAL_TZ) - timedelta(days=365):
            return {'start_time': start_time, 'end_time': end_time}

        if not bool(int(eventTku['is_hobby'])):
            eid = int(eventTku['drupal_nid'])
            eventItem = events[eid]
            eventItem['id'] = '%s:%s' % (self.data_source.id, eid)
            eventItem['origin_id'] = eid
            eventItem['data_source'] = self.data_source
            eventItem['publisher'] = self.organization
            eventItem['end_time'] = end_time

            #typeOfEvent = eventTku['event_type']

            event_categories = eventItem.get('event_categories', set())

            if event_categories:
                pass
            else:
                logger.info("No event_categories found for current event. Skipping...")

            ok_tags = ('u', 'b', 'h2', 'h3', 'em', 'ul', 'li', 'strong', 'br', 'p', 'a')

            eventItem['name'] = {"fi": eventTku['title_fi'], "sv": eventTku['title_sv'], "en": eventTku['title_en']}

            eventItem['description'] = {
                "fi": bleach.clean(self.with_value(eventTku, 'description_markup_fi', ''),   tags=[],   strip=True),
                "sv": bleach.clean(self.with_value(eventTku, 'description_markup_sv', ''),   tags=[],   strip=True),
                "en": bleach.clean(self.with_value(eventTku, 'description_markup_en', ''),   tags=[],   strip=True)
            }

            eventItem['short_description'] = {
                "fi": bleach.clean(self.with_value(eventTku, 'lead_paragraph_markup_fi', ''),   tags=[],   strip=True),
                "sv": bleach.clean(self.with_value(eventTku, 'lead_paragraph_markup_sv', ''),   tags=[],   strip=True),
                "en": bleach.clean(self.with_value(eventTku, 'lead_paragraph_markup_en', ''),   tags=[],   strip=True)
            }

            eventItem['provider'] = {"fi": 'Turku', "sv": 'Åbo', "en": 'Turku'}

            location_extra_info = ''

            if self.with_value(eventTku, 'address_extension', ''):
                location_extra_info += '%s, ' % bleach.clean(self.with_value(eventTku, 'address_extension', ''), tags=[], strip=True)
            if self.with_value(eventTku, 'city_district', ''):
                location_extra_info += '%s, ' % bleach.clean(self.with_value(eventTku, 'city_district', ''), tags=[], strip=True)
            if self.with_value(eventTku, 'place', ''):
                location_extra_info += '%s' % bleach.clean(self.with_value(eventTku, 'place', ''), tags=[], strip=True)

            if location_extra_info.strip().endswith(','):
                location_extra_info = location_extra_info.strip()[:-1]

            eventItem['location_extra_info'] = {
                "fi": location_extra_info if location_extra_info else None,
                "sv": location_extra_info if location_extra_info else None,
                "en": location_extra_info if location_extra_info else None
            }


            #eventItem['super_event_type'] = Event.SuperEventType.UMBRELLA

            event_image_ext_url = ''
            image_license = ''
            event_image_license = self.event_only_license

            #NOTE! Events image is not usable in Helmet must use this Lippupiste.py way to do it         
            if event_image_url:
                event_image_ext_url = event_image_url

                #event_image_license 1 or 2 (1 is 'event_only' and 2 is 'cc_by' in Linked Events) NOTE! CHECK VALUES IN DRUPAL!
                if eventTku['event_image_license']:
                    image_license = eventTku['event_image_license']
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

            eventItem['date_published'] = self.dt_parse(self.timeToTimestamp(str(eventTku['start_date'])))
            
            set_attr('start_time', self.dt_parse(self.timeToTimestamp(str(eventTku['start_date']))))
            set_attr('end_time', self.dt_parse(self.timeToTimestamp(str(eventTku['end_date']))))


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

            if eventTku['event_categories'] != None:
                eventTku['event_categories'] =eventTku['event_categories'] + ','
                categories = eventTku['event_categories'].split(',')
                for name in categories:
                    if name in TURKU_DRUPAL_CATEGORY_EN_YSOID.keys():
                        ysoId = TURKU_DRUPAL_CATEGORY_EN_YSOID[name]
                        event_keywords.add(Keyword.objects.get(id= ysoId))

            if eventTku['keywords'] != None:
                eventTku['keywords'] =eventTku['keywords'] + ','
                keywords = eventTku['keywords'].split(',')
                notFoundKeys = []
                for name in keywords:
                    if name not in TURKU_DRUPAL_CATEGORY_EN_YSOID.keys():
                        try:                
                            event_keywords.add(Keyword.objects.get(name = name))
                        except:
                            #print('Warning!' + ' keywords not found:' + name)
                            #logger.warning('Moderator should add the following keywords ' + name)
                            if name != "":
                                notFoundKeys.append(name)
                            pass
                if len(notFoundKeys) != 0:
                    logger.warning('Moderator should add the following keywords: ' \
                    +str(notFoundKeys)+' for Event ID: ' \
                    +str(eventTku['drupal_nid']) \
                    +" with Event Name: " +str(eventTku['title_fi'])
                    )


            eventItem['keywords'] = event_keywords



            if eventTku['target_audience'] != None:
                eventTku['target_audience'] =eventTku['target_audience'] + ','
                audience = eventTku['target_audience'].split(',')
                for name in audience:
                    if name in TURKU_DRUPAL_AUDIENCES_KEYWORD_EN_YSOID.keys():
                        ysoId = TURKU_DRUPAL_AUDIENCES_KEYWORD_EN_YSOID[name]
                        event_audience.add(Keyword.objects.get(id= ysoId))

            eventItem['audience'] = event_audience


            tprNo = ''

            if eventTku.get('event_categories', None):
                node_type = eventTku['event_categories'][0]
                if node_type == 'Virtual events':
                    eventItem ['location']['id'] = VIRTUAL_LOCATION_ID
                elif str(eventTku['palvelukanava_code']):
                    tprNo = str(eventTku['palvelukanava_code'])
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
                    if eventTku['address']:
                        import re
                        event_address = copy(eventTku['address'])
                        event_address_name = copy(eventTku['address'])
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
            if eventTku['drupal_nid_super']:
                eventItem['super_event_id'] = eventTku['drupal_nid_super']
                del eventTku['drupal_nid_super']
            '''


            if eventType == "mother" or eventType == "single":

                # Add a default offer
                free_offer = {
                    'is_free': True,
                    'price': None,
                    'description': None,
                    'info_url': None,
                    }

                eventOffer_is_free = bool(int(eventTku['free_event']))
                #Fill event_offer table information if events is not free price event
                if not eventOffer_is_free:

                    free_offer['is_free'] = False
                    if eventTku['event_price']: 
                        ok_tags = ('u', 'b', 'h2', 'h3', 'em', 'ul', 'li', 'strong', 'br', 'p', 'a')
                        price = str(eventTku['event_price'])                 
                        price = bleach.clean(price, tags= ok_tags, strip=True)
                        free_offer_price = clean_text(price, True)

                        free_offer['price'] = {'fi': free_offer_price}
                        free_offer['info_url'] =  {'fi': None}


                    if str(eventTku['buy_tickets_url']): 
                        free_offer_buy_tickets = eventTku['buy_tickets_url']
                        free_offer['info_url'] =  {'fi': free_offer_buy_tickets}

                    free_offer['description'] = None

                eventItem['offers'] = [free_offer]

            if eventType == "mother":
                eventItem['super_event_type'] = Event.SuperEventType.RECURRING

            if eventType == "child":
                eventItem['super_event_type'] = ""

            if eventType == "single":
                eventItem['super_event_type'] = ""
            #if eventType == "child":
            #    logger.info("this is a child")
            #    eventItem['super_event_type'] = ""
            #    for x in childList:
            #        print("WSDAOPFKASDOPFKOPDASKOPFDKSF SDOAK FOPSD KAOPFSD KAOPF KDSOPAF KSDOPAF KDOP ")
            #        for k, v in x.items():
            #            if k == eventTku['drupal_nid']:
            #                eventItem['super_event'] = str(v)


            return eventItem

    def _recur_fetch_paginated_url(self, url, lang, events):
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
                global drupal_json_response
                drupal_json_response = root_doc
                time.sleep(2)
            except ValueError:
                logger.warning("tku Drupal orig API returned invalid JSON (try {} of {})".format(try_number + 1, max_tries))
                if self.cache:
                    self.cache.delete_url(url)
                    time.sleep(1)
                    continue
            break
        else:
            logger.error("tku Drupal orig API broken again, giving up")
            raise APIBrokenError()

        json_root_event = root_doc['events']

        earliest_end_time = None
        event_image_url = None

        '''
        #This section of the code loops through all the events in the drupal JSON.
        for json_mother_event in json_root_event:
            json_event = json_mother_event['event']
            if json_event['event_image_ext_url']:
                event_image_url = json_event['event_image_ext_url']['src']
            else:
                event_image_url = ""
            #if json_event['event_type'] == "Single event" or json_event['event_type'] == "Event series":
            #Needs a logic to import mother events if their children can find it in the JSON.
            evntMother = [x for x in json_root_event if x['drupal_nid_super'] == json_event['drupal_nid']] 
            if json_event['event_type'] == "Single event":
                event = self._import_event(lang, json_event, events, event_image_url)
        
        now = datetime.now().replace(tzinfo=LOCAL_TZ)
        '''

        #Preprocess Children and Mothers.
        for json_mother_event in json_root_event:
            json_event = json_mother_event['event']

            if json_event['event_type'] == "Recurring event (in series)":
                curMotherToBeFound = json_event['drupal_nid_super']
                curChildNid = json_event['drupal_nid']

                for json_mother_event1 in json_root_event:
                    json_event1 = json_mother_event1['event']

                    if json_event1['drupal_nid'] == curMotherToBeFound:

                        if curMotherToBeFound not in mothersList:
                            mothersList.append(curMotherToBeFound)

                        if curMotherToBeFound in mothersList:
                            childList.append({curChildNid : curMotherToBeFound})

        #Process #1: Add Singles.
        for json_mother_event in json_root_event:
            json_event = json_mother_event['event']
            event_type = "single"

            if json_event['event_image_ext_url']:
                event_image_url = json_event['event_image_ext_url']['src']
            else:
                event_image_url = ""

            if json_event['event_type'] == 'Single event':
                event = self._import_event(lang, json_event, events, event_image_url, event_type, mothersList, childList)

        #Process #2: Add Mothers.
        for json_mother_event in json_root_event:
            json_event = json_mother_event['event']
            event_type = "mother"

            if json_event['drupal_nid'] in mothersList: #-> If event is a mother.

                if json_event['event_image_ext_url']:
                    event_image_url = json_event['event_image_ext_url']['src']
                else:
                    event_image_url = ""
                event = self._import_event(lang, json_event, events, event_image_url, event_type, mothersList, childList)

        #Process #3: Add Children.
        for json_child_event in json_root_event:
            json_event = json_child_event['event']
            event_type = "child"

            for x in childList:
                for k, v in x.items():
                    if json_event['drupal_nid'] == str(k): #-> If event is a child.

                        if json_event['event_image_ext_url']:
                            event_image_url = json_event['event_image_ext_url']['src']
                        else:
                            event_image_url = ""

                        event = self._import_event(lang, json_event, events, event_image_url, event_type, mothersList, childList)

        now = datetime.now().replace(tzinfo=LOCAL_TZ)

    def saveChildElement(self, drupal_url):

        json_root_event = drupal_url['events']
        for json_mother_event in json_root_event:
            json_event = json_mother_event['event']
            print(json_event['drupal_nid'])

            if json_event['drupal_nid']:
                #print(curEventElement['drupal_nid'])
                for x in childList:
                    for k, v in x.items():
                        if json_event['drupal_nid'] == k:
                            # -> 
                            logger.info("Saving child!")
                            try:
                                try:
                                    child = Event.objects.get(origin_id=k)
                                except Exception as ex: print(ex)
                                try:
                                    mother = Event.objects.get(origin_id=v)
                                except Exception as ex: print(ex)

                                Event.objects.update_or_create(
                                    id = child.id,
                                    defaults = {
                                    'date_published' : datetime.now(),
                                    'provider' : mother.provider,
                                    'provider_fi' : mother.provider_fi,
                                    'provider_sv' : mother.provider_sv,
                                    'provider_en' : mother.provider_en,
                                    'description' : mother.description,
                                    'description_fi' : mother.description_fi,
                                    'description_sv' : mother.description_sv,
                                    'description_en' : mother.description_en,
                                    'short_description' : mother.short_description,
                                    'short_description_fi' : mother.short_description_fi,
                                    'short_description_sv' : mother.short_description_sv,
                                    'short_description_en' : mother.short_description_en,
                                    'location_id' : mother.location_id,
                                    'location_extra_info' : mother.location_extra_info,
                                    'location_extra_info_fi' : mother.location_extra_info_fi,
                                    'location_extra_info_sv' : mother.location_extra_info_sv,
                                    'location_extra_info_en' : mother.location_extra_info_en,
                                    'super_event' : mother}
                                    )
                            except Exception as ex: print(ex)
                            try:
                                logger.info("Updating childs Offer values.")
                                # -> Get object from Event.
                                try:
                                    child = Event.objects.get(origin_id=k)
                                except Exception as ex: print(ex)
                                try:
                                    mother = Event.objects.get(origin_id=v)
                                except Exception as ex: print(ex)
                                # -> Get object from Offer once we have the Event object.
                                try:
                                    motherOffer = Offer.objects.get(event_id=mother.id)

                                    Offer.objects.update_or_create(
                                            event_id=child.id,
                                            price=motherOffer.price,
                                            info_url=motherOffer.info_url,
                                            description=motherOffer.description,
                                            is_free=motherOffer.is_free
                                            )
                                except Exception as ex: print(ex)

                                #try:
                                #    childOffer = Offer.objects.get(event_id=child.id)
                                #except Exception as ex: print(ex)
                            except Exception as ex: print(ex)


            #Facebook urls for either singles or mother events.
            if json_event['facebook_url']:
                originid = json_event['drupal_nid']
                #get event object
                try:
                    myLang = Language.objects.get(id="fi")
                except:
                    pass
                try:
                    eventObj = Event.objects.get(origin_id=originid)
                    print(eventObj.id)

                    EventLink.objects.update_or_create(
                        name="extlink_facebook",
                        event_id=eventObj.id,
                        language_id=myLang.id,
                        link=json_event['facebook_url']
                        )
                    logger.info("FACEBOOK!!")

                    # ->  Add children of the mother to the EventLink table...
                    for x in mothersList:
                        if x == json_event['drupal_nid']:
                            for g in childList:
                                for k, v in g.items():
                                    if v == x:
                                        try:
                                        # -> k is the child of the mother. Add k into EventLink
                                            eventChildObj = Event.objects.get(origin_id=k)
                                            EventLink.objects.update_or_create(
                                                name="extlink_facebook",
                                                event_id=eventChildObj.id,
                                                language_id=myLang.id,
                                                link=json_event['facebook_url']
                                                )
                                            logger.info("FACEBOOK CHILD!!!")
                                        except:
                                            pass
                except:
                    pass
            if json_event['twitter_url']:
                originid = json_event['drupal_nid']
                #get event object
                try:
                    myLang = Language.objects.get(id="fi")
                except:
                    pass
                try:
                    eventObj = Event.objects.get(origin_id=originid)
                    print(eventObj.id)

                    EventLink.objects.update_or_create(
                        name="extlink_twitter",
                        event_id=eventObj.id,
                        language_id=myLang.id,
                        link=json_event['twitter_url']
                        )
                    logger.info("TWITTER!!")

                    # ->  Add children of the mother to the EventLink table...
                    for x in mothersList:
                        if x == json_event['drupal_nid']:
                            for g in childList:
                                for k, v in g.items():
                                    if v == x:
                                        
                                        try:
                                        # -> k is the child of the mother. Add k into EventLink
                                            eventChildObj = Event.objects.get(origin_id=k)
                                            EventLink.objects.get_or_create(
                                                name="extlink_twitter",
                                                event_id=eventChildObj.id,
                                                language_id=myLang.id,
                                                link=json_event['twitter_url']
                                                )
                                            logger.info("TWITTER CHILD!!!")
                                        except:
                                            pass
                except:
                    pass
            
            #if json_event['website_url']:
            #    eventItem['info_url'] = {"fi": eventTku['website_url'], "sv": eventTku['website_url'], "en": eventTku['website_url']}

            '''
            # -> Add children of the mothers into the sociallinks table (inheritance).
            if json_event['event_type'] == 'Recurring event (in series)':
                superid = json_event['drupal_nid_super']
                try:
                    myLang = Language.objects.get(id="fi")
                except:
                    pass
                try:
                    # -> Find superid (child events mother) event in EventLink.
                    childsMomEvent = Event.objects.get(origin_id=superid)
                    childsMom = EventLink.objects.get(event_id=childsMomEvent.id)
                    try:
                        #get child object in Event, then write it into sociallinks table.
                        eventObj = Event.objects.get(origin_id=superid)
                        print(eventObj.id)
                        EventLink.objects.update_or_create(
                            name="extlink_twitter",
                            event_id=eventObj.id,
                            language_id=childsMom.language_id,
                            link=eventObj.id
                            )
                        logger.info("TWITTER!!")
                    except:
                        pass
                except:
                    pass
            '''
            #Add facebook and twitter url for children:
            #try
    

    def import_events(self):
        import requests
        logger.info("Importing old Turku events...")
        events = recur_dict()

        url = TKUDRUPAL_BASE_URL
        
        lang = self.supported_languages

        try:
            self._recur_fetch_paginated_url(url, lang, events)
        except APIBrokenError:
            return


        logger.info("Test phase 1")
        event_list = sorted(events.values(), key=lambda x: x['end_time'])
        logger.info("Test phase 2")
        qs = Event.objects.filter(end_time__gte=datetime.now(), data_source='turku')
        logger.info("Test phase 3")
        self.syncher = ModelSyncher(qs, lambda obj: obj.origin_id, delete_func=set_deleted_false)
        logger.info("Test phase 4")

        for event in event_list:
            try:
                obj = self.save_event(event)
                self.syncher.mark(obj)
            except:
                ...

        #self.syncher.finish(force=True)

        #Update childrens super_event_id
        print("Trying to save children....")

        url = drupal_json_response

        try:
            self.saveChildElement(url)
        except APIBrokenError:
            return

        self.syncher.finish(force=True)


        #try:
        #    self.saveChildElement(url, lang)
        #except APIBrokenError:
            #return

        #self.syncher.finish(force=True)
        logger.info("%d events processed" % len(events.values()))
