# Nexvision search engine

## Features

* Crawls the darknet looking for new hidden service
* Find hidden services from a number of clear net sources
* Optional full-text Elasticsearch support
* Marks clone sites of the /r/darknet super list
* Finds SSH fingerprints across hidden services
* Finds email addresses across hidden  services
* Finds bitcoin addresses across hidden services
* Shows incoming / outgoing links to onion domains
* Up-to-date alive/dead hidden service status
* Portscanner
* Search for "interesting" URL paths, useful 404 detection
* Automatic language detection
* Fuzzy clone detection (requires Elasticsearch, more advanced than super list clone detection)


## Components

### Elasticsearch

Elasticsearch cluster consists of 2 Elasticsearch instance for HA and load balancing.
The scrapped page data is stored and searched.

### Kibana

It runs on port 5601 and can be used to check the data in Elasticsearch

### Web-General

The web interface for domain search engine. It runs on port 7000

### MySQL

It stores the domains, page urls, bitcoin addresses, etc.

### TOR Proxy

Used to access the onion pages. There are 10 proxy containers deployed and HAProxy is used to distribute the traffic.

### Scraper

It gets the domain list from MySQL DB, harvest pages and new domains from onion domains through TOR proxies and stores the domains and page data in Elasticsearch and MySQL.
Based on Python Scrapy framework.



## Installation

Clone the project and build docker images involved in docker-compose.

    docker-compose build
    docker-compose up -d

Build and run the scraper.

    docker build --tag scraper_crawler ./

Run the scraper.

    docker run -d --name darkweb-search-engine-onion-crawler --network=darkweb-search-engine_default scraper_crawler /opt/torscraper/scripts/start_onion_scrapy.sh

After first deployment, need to initialize the indexes on Elasticsearch.

    docker exec darkweb-search-engine-onion-crawler /opt/torscraper/scripts/elasticsearch_migrate.sh

Import initial domain list

    docker exec darkweb-search-engine-onion-crawler /opt/torscraper/scripts/push_list.sh /opt/torscraper/onions_list/onions.txt &

