# Linked Events

[![Build status](https://travis-ci.org/City-of-Helsinki/linkedevents.svg)](https://travis-ci.org/City-of-Helsinki/linkedevents)
[![codecov](https://codecov.io/gh/City-of-Helsinki/linkedevents/branch/master/graph/badge.svg)](https://codecov.io/gh/City-of-Helsinki/linkedevents)
[![Requirements](https://requires.io/github/City-of-Helsinki/linkedevents/requirements.svg?branch=master)](https://requires.io/github/City-of-Helsinki/linkedevents/requirements/?branch=master)
[![Gitter](https://img.shields.io/gitter/room/City-of-Helsinki/heldev.svg?maxAge=2592000)](https://gitter.im/City-of-Helsinki/heldev)

![High-level diagram of Linked Events](./assets/Linked_Events.jpg?raw=true)


#### TL;DR => Linked Events is a REST API which allows you to set up an _**event**_* publication hub.

\*_**event**_  here means a happening where people get together and do something.


Linked Events is event information:

  * *Aggregator* => using Python importers which have the logic to import events information from different data sources
  * *Creator* => by offering PUT/POST `/event` API endpoint with granular user permissions and a hierarchical organization structure supporting different publishing rights for different organizations
  * *Publisher* => by offering API endpoints from which interested parties can retrieve information about events

Linked Events was originally developed for City of Helsinki organization and
you can see the Linked Events API in action for [Helsinki capital region here](https://api.hel.fi/linkedevents/v1/).
It contains data from all Helsinki City Departments as well as data from Helsinki Marketing and the Helmet metropolitan area public libraries. Viewing the API should give a reasonable view for the kind of information Linked Events is targeted for.

Target audience of this README.md are developers who may or maynot have a lot of Python
experience and would like to get things running as quickly as possible.
Therefore, instructions written in this README.md should be written accordingly.

## Contributing

The best way to contribute is to open a new PR for discussion. We strive to be able to support various cities with various use cases, so suggestions and new features (as long as they fit in with existing functionality) are welcome.

## How to setup your local development environment
If all you want is a barebone application to work with for your own city:

* Start django application and database server:
  ```
  docker-compose up
  ```

* Access application on [localhost:8000](http://localhost:8000)

* You are done 🔥

If you wish to use locations, addresses and events data from the Helsinki capital region:

* Read [linked-events-importers.md](./linked-events-importers.md#linked-events-importers-and-commands) and decide the importers or commands you would like to use.

* You can then serve the [UI for Linked Events API](https://github.com/City-of-Helsinki/linkedevents-ui) for example by setting authentication keys to `local_settings.py`

* UI app is specific to Helsinki at the moment and requires general Finnish ontology as well as additional Helsinki specific audiences
and keywords to be present. However, UI code should be easily adaptable to your own city if you have an OAuth2 authentication server present


## Manual installation of Linked Events on physical or virtual machine:

Install following packages with your distros package manager
```bash
postgresql postgis nginx virtualenv python3-dev python3-pip build-essential libpq-dev
```

### Preparing your PostgreSQL:
	
Generate required locales
```bash
sudo locale-gen fi_FI.UTF-8
sudo systemctl restart postgresql
```		
Create a new role in postgresql
```bash
sudo -u postgres createuser -R -S linkedevents
```
Create a new database in postgresql
```bash
sudo -u postgres createdb -O linkedevents -T template0 -l fi_FI.UTF-8 linkedevents
```
Create extensions for the database
```bash
sudo -u postgres psql linkedevents -c "CREATE EXTENSION postgis;"
sudo -u postgres psql linkedevents -c "CREATE EXTENSION hstore;"
```
### Preparing your local repository:

Clone your repository
```bash
git clone https://github.com/City-of-Turku/linkedevents.git
```
Create a virtual environment for your python
```bash
virtualenv -p python3 venv
```
Activate your virtual environment
```bash
source venv/bin/activate
```
Install requirements.txt
```bash
pip install -r requirements.txt
```
Install requirements-dev.txt
```bash
pip install -r requirements-dev.txt
```
### Fill your database with included migrations:
	
Run basic migrations
```bash
python manage.py migrate
```
Additional changes to language fields according to settings.LANGUAGES
```bash
python manage.py sync_translation_fields
```

```bash
cd $INSTALL_BASE/linkedevents
# Import general Finnish ontology (used by Helsinki UI and Helsinki events)
python manage.py event_import yso --all
# Add keyword set to display in the UI event audience selection
python manage.py add_helsinki_audience
# Add keyword set to display in the UI main category selection
python manage.py add_helsinki_topics
# Import places from Helsinki metropolitan region service registry (used by events from following sources)
python manage.py event_import tprek --places
# Import places from Helsinki metropolitan region address registry (used as fallback locations)
python manage.py event_import osoite --places
# Import events from Helsinki metropolitan region libraries
python manage.py event_import helmet --events
# Import events from Espoo
python manage.py event_import espoo --events
# Import City of Helsinki hierarchical organization for UI user rights management
python manage.py import_organizations https://api.hel.fi/paatos/v1/organization/ -s helsinki:ahjo
# Import municipalities in Finland
python manage.py geo_import finland --municipalities
# Import districts in Helsinki
python manage.py geo_import helsinki --divisions
# install API frontend templates:
python manage.py install_templates helevents
```

The last command installs the `helevents/templates/rest_framework/api.html` template,
which contains Helsinki event data summary and license. You may customize the template
for your favorite city by creating `your_favorite_city/templates/rest_framework/api.html`.
For further erudition, take a look at the DRF documentation on [customizing the browsable API](http://www.django-rest-framework.org/topics/browsable-api/#customizing)

After this, everything but search endpoint (/search) is working. See [search](#search)

Production notes
----------------

Development installation above will give you quite a serviceable production installation for lightish usage. You can serve out the application using your favorite WSGI-capable application server. The WSGI-entrypoint for Linked Events is ```linkedevents.wsgi``` or in file ```linkedevents/wsgi.py```. Former is used by gunicorn, latter by uwsgi. The callable is ```application```.

You will also need to serve out ```static``` and ```media``` folders at ```/static``` and ```/media``` in your URL space.

Running tests
------------
Tests must be run using an user who can create (and drop) databases and write the directories
your linkedevents installation resides in. Also the template database must include Postgis and
HSTORE-extensions. If you are developing, you probably want to give those
permissions to the database user configured in your development instance. Like so:

```bash
# Change this if you have different DB user
DATABASE_USER=linkedevents
# Most likely you have a postgres system user that can log into postgres as DB postgres user
sudo -u postgres psql << EOF
ALTER USER "$DATABASE_USER" CREATEDB;
\c template1
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS hstore;
EOF

```

Afterwards you can run the tests:
```bash
cd $INSTALL_BASE/linkedevents
py.test events
```

Note that search tests will fail unless you configure [search](#search)

Requirements
------------

Linked Events uses two files for requirements. The workflow is as follows.

`requirements.txt` is not edited manually, but is generated
with `pip-compile`.

`requirements.txt` always contains fully tested, pinned versions
of the requirements. `requirements.in` contains the primary, unpinned
requirements of the project without their dependencies.

In production, deployments should always use `requirements.txt`
and the versions pinned therein. In development, new virtualenvs
and development environments should also be initialised using
`requirements.txt`. `pip-sync` will synchronize the active
virtualenv to match exactly the packages in `requirements.txt`.

In development and testing, to update to the latest versions
of requirements, use the command `pip-compile`. You can
use [requires.io](https://requires.io) to monitor the
pinned versions for updates.

To remove a dependency, remove it from `requirements.in`,
run `pip-compile` and then `pip-sync`. If everything works
as expected, commit the changes.

Search
------
Linkedevents uses Elasticsearch for generating results on the /search-endpoint. If you wish to use that functionality, proceed like so:

1. Install elasticsearch

    We've only tested using the rather ancient 1.7 version. Version 5.x will certainly not work as the `django-haystack`-library does not support it. If you are using Ubuntu 16.04, 1.7 will be available in the official repository.

2. (For Finnish support) Install elasticsearch-analyzer-voikko, libvoikko and needed dictionaries

    `/usr/share/elasticsearch/bin/plugin -i fi.evident.elasticsearch/elasticsearch-analysis-voikko/0.4.0`
    This specific command is for Debian derivatives. The path to `plugin` command might be different on yours. Note that version 0.4.0 is the one compatible with Elasticsearch 1.7

    Installing libvoikko:
    `apt-get install libvoikko1`

    Installing the dictionaries (v5 dictionaries are needed for libvoikko version included in Ubuntu 16.04):

    ```
    wget -P $INSTALL_BASE http://www.puimula.org/htp/testing/voikko-snapshot-v5/dict-morpho.zip
    unzip $INSTALL_BASE/dict-morpho.zip -d /etc/voikko
    ```

3. Configure the thing

    Set the `ELASTICSEARCH_URL` environment variable (or variable in `config_dev.toml`, if you are running in development mode) to your elasticsearch instance. The default value is `http://localhost:9200/`.

    Haystack configuration for all Linkedevents languages happens automatically if `ELASTICSEARCH_URL` is set, but you may customize it manually using `local_settings.py` if you know Haystack and wish to do so.

4. Rebuild the search indexes

   `python manage.py rebuild_index`

   You should now have a working /search endpoint, give or take a few.

Event extensions
----------------

It is possible to extend event data and API without touching `events` application by implementing separate extension applications. These extensions will be wired under field `extension_<extension idenfier>` in event API. If not auto enabled (see 6. below), extensions can be enabled per request using query param `extensions` with comma separated identifiers as values, or `all` for enabling all the extensions.

To implement an extension:

1) Create a new Django application, preferably named `extension_<unique identifier for the extension>`.

2) If you need to add new data for events, implement that using model(s) in the extension application.

3) Inherit `events.extensions.EventExtension` and implement needed attributes and methods. See [extensions.py](events/extensions.py) for details.

4) Add `event_extension: <your EventExtension subclass>` attribute to the extension applications's `AppConfig`.

5) Make the extension available by adding the extension application to `INSTALLED_APPS`.

6) If you want to force the extension to be enabled on every request, add the extension's identifier to `AUTO_ENABLED_EXTENSIONS` in Django settings.

For an example extension implementation, see [course extension](extension_course).
