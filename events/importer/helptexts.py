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
    'location': {
        'sidefield': {
            'general': {
                'fi': """Tapahtuma voi olla virtuaalinen, lähitapahtuma tai molemmat. 
                <br><strong>Jos tapahtuma järjestetään etänä internetissä, valitse tapahtumapaikaksi 
                Virtuaalitapahtuma ja syötä URL-osoite. Lähitapahtumassa voit antaa lisätietoja tapahtumapaikan löytämiseksi, esimerkiksi konferenssihuoneen nimen tai ohjeet sisäänkäynnille.</strong><br>
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
            'course': {
                'fi': """Opetus voidaan järjestää etänä, lähikoulutuksena tai kummallakin tavoin.
                <br><strong>Jos opetus järjestetään etänä internetissä, valitse paikaksi Etäkoulutus ja syötä URL-osoite. 
                Lähiopetuksessa voit antaa lisätietoja paikan löytämiseksi, 
                esimerkiksi luokkahuoneen nimen tai ohjeet sisäänkäynnille.</strong><br>
                Jos tarkkaa koulutuspaikkaa ei löydy listasta, valitse paikaksi lähin katuosoite ja kirjoita paikan nimi
                tai muut tarkemmat saapumisohjeet tiiviisti lisätietokenttään.""",

                'sv': """Undervisningen kan hållas som distansundervisning, fysiskt på plats eller både och.
                <br><strong>Om utbildningen hålls på distans på Internet, välj Distansträning som plats och ange URL. 
                I klassrumsundervisningen kan du ge ytterligare information för att hitta en plats, 
                till exempel namnet på klassrummet eller vägbeskrivning till entrén.</strong><br>
                Utbildning: Om den exakta träningsplatsen inte kan hittas i listan, 
                välj närmaste gatuadress som plats och ange ortens namn eller andra 
                detaljerade instruktioner i fältet för ytterligare information.""",

                'en': """Teaching can be provided remotely, face-to-face, or both.
                <br><strong>If the teaching is arranged remotely, select Remotely as the location, and enter a URL. 
                For face-to-face teaching you can enter details about the exact location, 
                for example the instructions to find the entrance or the name / number of the classroom.</strong><br>
                If you can't find the exact venue, then choose the nearest street address and enter the venue 
                name or arrival instructions in the additional information field."""
            },
            'hobbies': {
                'fi': """Harrastus on yleensä fyysisesti paikan päällä tapahtuva.
                <br><strong>Jos harrastus järjestetään etänä internetissä, valitse harrastuspaikaksi 
                "Virtuaalinen harrastus" ja syötä URL-osoite. Paikan päällä tapahtuvaa harrastusta 
                varten voit antaa lisätietoja harrastuspaikan löytämiseksi, 
                esimerkiksi ohjeet sisäänkäynnille tai liikuntasalin nimen / numeron.</strong><br>
                Jos tarkkaa harrastuspaikkaa ei löydy listasta, valitse paikaksi lähin katuosoite ja kirjoita 
                paikan nimi tai muut tarkemmat saapumisohjeet tiiviisti lisätietokenttään.""",

                'sv': """Hobbyn ordnas vanligen fysiskt på plats.
                Om hobbyn ordnas på distans över internet, välj då Virtuell hobby som hobbyplats, 
                samt mata in en URL. För hobbyn som ordnas fysiskt på plats så kan du ange ytterligare 
                information för att hitta hobbyplatsen, till exempel instruktioner för att hitta ingången 
                eller gymnastiksalens namn / nummer.</strong><br>
                Om en exakt hobbyplats inte finns på listan, välj då närmaste gatuadress och skriv 
                platsens namn eller ankomstinstruktioner i fältet för tilläggsuppgifter.""",

                'en': """Hobbies are usually onsite events.
                <br><strong>If the hobby is virtual on the Internet, select Virtual hobby as the location and enter a URL. 
                For onsite hobbies, you can enter details about the exact location, for example the instructions 
                to find the entrance or the name / number of the sports hall.</strong><br>
                If you can't find the exact venue, then choose the nearest street address and enter the 
                venue name or arrival instructions in the additional information field."""
            },
        },
        'mobile': {
            'fi': "Paikan valinnan ohjeet",
            'sv': "Anvisningen om att välja plats",
            'en': "Instructions for selecting a location"
        }
    },
    'umbrella': {
        'sidefield': {
            'general': {
                'fi': """Kattotapahtuma: tapahtuma kokoaa alleen useita muita tapahtumia. 
                Esim. Taiteiden yö tai Elokuvapäivä.<br>
                Liittyy kattotapahtumaan: tapahtuma liittyy suoraan isompaan tapahtumaan. 
                Esim. Kirjailijatapaaminen Taiteiden yönä.""",

                'sv': """Paraplyevenemang: evenemanget är en samling flera evenemang. T.ex Konstens natt.<br>
                Del av ett paraplyevenemang: evenemanget är en del av ett större evenemang. 
                T.ex Författarträff under Konstens natt.""",

                'en': """Umbrella event: the event brings together several other events. 
                For example, Night of the Arts or Movie Day.<br>
                Part of an umbrella event: The event is a part of a larger event. 
                For example, Meet with the Writer on Night of the Arts."""
            },
            'course': {
                'fi': """Koulutukset ovat yleensä itsenäisiä kokonaisuuksia. 
                Koulutuksen kattoteema kokoaa alleen useita tähän teemaan liittyviä koulutuksia.<br>
                Liittyy kattoteemaan.""",

                'sv': """Utbildning är vanligtvis en självständig enhet. 
                Utbildningens paraplytema samlar flera utbildningar relaterade till detta tema.<br>
                Relaterat till temat takutbildning: Utbildningen är en del av ett större tema.""",

                'en': """Education is usually an independent entity. 
                The umbrella theme of the training brings together several trainings related to this theme.<br>
                Related to the roof theme: The education is a part of a larger theme."""
            },
            'hobbies': {
                'fi': """Harrastukset ovat yleensä itsenäisiä kokonaisuuksia. 
                Harrastuksen kattoteema: Kattoteema kokoaa alleen useita tähän teemaan liittyviä harrastuksia.
                Esim. Kivakesä kulmilla.<br>
                Liittyy kattoteemaan: Esim. Kivakesä kulmilla -ohjelmaan kuuluva Tanssipaja Lausteella.""",

                'sv': """Hobbyer är vanligen självständiga helheter. 
                Paraplyevenemang = Evenemanget är en samling flera hobbyer. 
                T.ex. Sommarskoj i knutarna.<br>
                Del av ett paraplyevenemang: Hobbyn är en del av en större helhet. 
                T.ex. Dansworkshop i Laustis, som hör till Sommarskoj i knutarna -programmet.""",

                'en': """Hobbies are usually independent. Hobby theme: Theme brings together several hobbies, 
                that belong to the same theme. For example “Kivakesä kulmilla”.<br>
                Related to the roof them: The hobby is a part of a larger theme."""
            },
        },
        'mobile': {
            'fi': "Kattotapahtuman ohjeet",
            'sv': "Anvisningen om ett paraplyevenemang",
            'en': "Instructions for an umbrella event"
        }
    },
    'times': {
        'sidefield': {
            'general': {
                'fi': """Valitse onko tapahtumasi yksittäinen vai sarjatapahtuma.<br>
                Sarjatapahtuma koostuu alitapahtumista, joita voi olla vähintään 2 ja enintään 65.<br>
                Lisää uusi ajankohta: lisää alitapahtumia sarjatapahtumaan.<br>
                Säännöllisesti toistuva tapahtuma: lisää esimerkiksi viikoittain, 
                samoina päivinä toistuvia tapahtumakertoja (esim. teatterinäytös, joka toistuu 
                useita kertoja samanlaisena eri päivinä).""",

                'sv': """Välj mellan en enskild eller återkommande evenemang.<br>
                En evenemang serie består av flera evenemangstillfällen, 
                det måste innehålla mellan 2 och 65 evenemang.<br>
                Lägg till en ny tidpunkt: Lägg till återkommande evenemang till en serie.<br>
                Ett regelbundet återkommande evenemang: Lägg till regelbundet återkommande tider 
                som upprepas t.ex varje vecka (bl.a. en teaterföreställning som 
                upprepas likadan flera gånger).""",

                'en': """Choose whether your event is a single event or a serial event.<br>
                A serial event consists of multiple sub-events, 
                it may contain at least 2 and up to 65 sub-events.<br>
                Add new occasion: add sub-events to a serial event.<br>
                Regularly recurring event: Add regularly recurring events, e.g. a weekly."""
            },
            'course': {
                'fi': """Valitse onko koulutuksesi yksittäinen vai sarja.<br>
                Sarja koostuu koulutuskerroista, joita voi olla vähintään 2 ja enintään 65.<br>
                Lisää uusi ajankohta: jos koulutuksen ajankohdat eivät 
                noudata säännöllistä toistuvuutta, lisää yksittäisiä kertoja koulutussarjaan.<br>
                Säännöllisesti toistuva koulutussarja: lisää esimerkiksi viikoittain, 
                samoina päivinä toistuvia koulutuskertoja.""",

                'sv': """Välj mellan en enskild eller en återkommande utbildning.<br>
                En utbildnings serie består av flera utbildningstillfällen, 
                det måste innehålla mellan 2 och 65 tillfällen.<br>
                Lägg till en ny tidpunkt: Lägg till enskilda 
                utbildningstillfällen till utbildnings serien.<br>
                En regelbundet återkommande utbildning: Lägg till regelbundet 
                återkommande tider som upprepas t.ex. varje vecka.""",

                'en': """Choose whether the education is a single function or an education series.<br>
                A education series consists of multiple occurances, it may contain at least 2 and up to 65.<br>
                Add new occasion: add occurrence to an education series.<br>
                Regularly recurring education: add regularly, eg. weekly, recurring education."""
            },
            'hobbies': {
                'fi': """Valitse onko harrastuksesi yksittäinen vai sarja.<br>
                Sarja koostuu harrastuskerroista, joita voi olla vähintään 2 ja enintään 65.<br>
                Lisää uusi ajankohta: Jos harrastuskerrat eivät noudata säännöllistä toistuvuutta, 
                lisää yksittäisiä harrastuskertoja sarjaan.<br>
                Säännöllisesti toistuva harrastus: Lisää esimerkiksi viikoittain, 
                samoina päivinä toistuvia harrastuskertoja.""",

                'sv': """Välj mellan en enskild eller en återkommande hobby.<br>
                En hobby serie består av flera hobbytillfällen, det måste innehålla mellan 2 och 65 tillfällen.<br>
                Lägg till en ny tidpunkt: Lägg till ett tillfälle till en återkommande hobby.<br>
                En regelbundet återkommande hobby: Lägg till regelbundet återkommande 
                tider som upprepas t.ex. varje vecka.""",

                'en': """Choose whether the hobby is a single function or a hobby series.<br>
                A hobby series consists of multiple occurances, it may contain at least 2 and up to 65.<br>
                Add new occasion: Add occurance to a hobby series.<br>
                Regularly recurring hobby: Add regularly, eg. weekly, recurring hobby."""
            },
        },
        'mobile': {
            'fi': "Tapahtumien toistuvuuden ohjeet",
            'sv': "Anvisningen om evenemangets repetition",
            'en': "Instructions for choosing event recurrence"
        }
    },
    'offers': {
        'sidefield': {
            'multitype': {
                'fi': """HUOM! Ensimmäisen hintatiedon maksutavat periytyvät muihin hintatietoihin 
                lomakkeen tallennuksen yhteydessä jos niillä ei ole maksutapoja.""",

                'sv': """OBS! Den första prisinformationens betalningsmetoder ärvs av alla andra prisinformation 
                om de inte har betalningsmetoder då evenemanget sparas.""",

                'en': """Notice! The payment methods from the first price information are inherited 
                by the others if they don't have any payment methods when the event is saved."""
            },
        },
        'mobile': {
            'fi': "Hintatietojen ohjeet",
            'sv': "Anvisning om prisuppgifter",
            'en': "Instructions for entering price details"
        }
    },
    'keyword': {
        'sidefield': {
            'general': {
                'fi': """Valitse asiasanoja, jotka kuvaavat tapahtumaa mahdollisimman tarkasti 
                (esimerkiksi musiikin sijaan lastenmusiikki). Usein kuvailuun riittää 1-5 asiasanaa.""",

                'sv': """Välj ämnesord som beskriver evenemanget så exakt som möjligt 
                (t.ex. barnmusik istället för musik). 1-5 ämnesord brukar räcka 
                till för att beskriva evenemang.""",

                'en': """Choose keywords to describe the event as accurately as possible 
                (for example, children's music instead of music). Usually 1-5 keywords are enough."""
            },
            'course': {
                'fi': """Valitse asiasanoja, jotka kuvaavat koulutusta mahdollisimman tarkasti 
                (esimerkiksi musiikin sijaan lastenmusiikki). Usein kuvailuun riittää 1-5 asiasanaa.""",

                'sv': """Välj ämnesord som beskriver utbildningen så exakt som möjligt 
                (t.ex. barnmusik istället för musik). 1–5 ämnesord brukar räcka 
                till för att beskriva hobbyn.""",

                'en': """Choose keywords to describe the education as accurately as possible 
                (for example, children's music instead of music). Usually, 1-5 keywords are enough."""
            },
            'hobbies': {
                'fi': """Valitse asiasanoja, jotka kuvaavat harrastusta mahdollisimman tarkasti 
                (esimerkiksi musiikin sijaan lastenmusiikki). Usein kuvailuun riittää 1-5 asiasanaa.""",

                'sv': """Välj ämnesord som beskriver hobbyn så exakt som möjligt (t.ex. barnmusik istället för musik). 
                1-5 ämnesord brukar räcka till för att beskriva hobbyn.""",

                'en': """Choose keywords to describe the hobby as accurately as possible 
                (for example, children's music instead of music). Usually 1-5 keywords are enough."""
            },
        },
        'mobile': {
            'fi': "Ohjeet asiasanojen valintaan",
            'sv': "Anvisning för val av ämnesord",
            'en': "Instructions for selecting keywords"
        }
    },
    'category': {
        'sidefield': {
            'general': {
                'fi': """Valitse tapahtuman sisältöä yleisellä tasolla kuvaava luokka. 
                Useimmiten kuvaukseen riittää yksi luokka, 
                mutta tarvittaessa voit valita useampia luokkia. 
                Valitse myös tapahtuman järjestämistapaa kuvaava luokka.""",

                'sv': """Välj kategori som övrigt beskriver evenemangets innehåll. 
                Vanligtvis så räcker det med en kategori men vid behov så kan flera kategorier också väljas. 
                Välj också innehållets typ som beskriver hur evenemanget ordnas.""",

                'en': """Select a category to describe the content of the event at a general level. 
                Usually one category is enough, but you can select more than one when necessary. 
                Also choose the type of event to describe how the event is organized."""
            },
            'course': {
                'fi': """Valitse koulutuksen sisältöä yleisellä tasolla kuvaava luokka. 
                Useimmiten kuvaukseen riittää yksi luokka.""",

                'sv': """Välj en kategori som beskriver innehållet i utbildningen på generell nivå. 
                Vanligtvis så räcker det med en kategori.""",

                'en': """Select a category to describe the content of the education at a general level. 
                Usually, one category is enough."""
            },
            'hobbies': {
                'fi': """Valitse harrastuksen sisältöä yleisellä tasolla kuvaava luokka. 
                Useimmiten kuvaukseen riittää yksi luokka.""",

                'sv': """Välj en kategori som beskriver innehållet i hobby på generell nivå. 
                Vanligtvis så räcker det med en kategori.""",

                'en': """Select a category to describe the content of the hobby at a general level. 
                Usually, one category is enough."""
            },
        },
        'mobile': {
            'fi': "Ohjeet luokkien valintaan",
            'sv': "Anvisning för val av kategori",
            'en': "Instructions for selecting categories"
        }
    },
}


@register_importer
class HelptextsImporter(Importer):
    # Importer class dependant attributes:
    name = 'helptexts'
    supported_languages = ('fi', 'sv', 'en')

    # Extra options.
    ignore_setup = True
    ignore_prerequisites = True

    type_ids = {'general': 1, 'course': 2, 'hobbies': 4}

    def __set_attr_values(self, target: Any, attr_names: List, texts: List) -> None:
        """Method for setting helptexts to the 3 Sidefield() objects db attributes. Passed by reference."""
        for idx in range(2):
            setattr(target, attr_names[idx], texts[idx])

    def _process_data(self, objs: dict) -> None:
        """The core logic, the processing phase."""
        for prefix, inner_field_data in data.items():
            for type_id, type_id_data in inner_field_data['sidefield'].items():
                for lang in self.supported_languages:
                    # The following variables are for the function arguments.
                    sidefield_mobile = ['%s_%s_%s' % (prefix, subfix, lang) for subfix in ('sidefield', 'mobile')]
                    texts = [type_id_data[lang], inner_field_data['mobile'][lang]]
                    if type_id == 'multitype':
                        for obj in objs:
                            self.__set_attr_values(target=objs[obj], attr_names=sidefield_mobile, texts=texts)
                    else:
                        self.__set_attr_values(target=objs[type_id], attr_names=sidefield_mobile, texts=texts)

    def _save(self) -> None:
        """Saving phase is our handler for this importer. 
        Saves / creates 3 different DB fields based on the type_ids."""

        # As a failsafe, we do not want to re-run this importer twice by accident:
        if Sidefield.objects.all().count() > 0:
            logger.error("Helptexts already exist, this importer is not built to be ran twice. Exiting!")
            return None

        # Create 3 associative objects and populate them with attributes in the processing phase:
        objs = {key: Sidefield() for key in self.type_ids}
        self._process_data(objs=objs)

        # Since this importer is only meant to be ran once, this will suffice:
        for type_name, obj in objs.items():
            obj.type_id = self.type_ids[type_name]
            obj.sidefieldset_name = type_name.capitalize()
            obj.save()
            logger.info("Helptext importer created a new sidefieldset: %s" % obj.sidefieldset_name)

    def __init__(self, options):
        proc_time_frmt('Initial')
        self._save()  # Handle.
        proc_time_frmt('Importer')
