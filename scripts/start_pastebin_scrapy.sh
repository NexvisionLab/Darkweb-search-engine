#!/bin/sh

export BASEDIR=/opt/torscraper
export ETCDIR=$BASEDIR/etc

export PYTHONPATH=$PYTHONPATH:$BASEDIR/lib

. $ETCDIR/database
export DB_HOST
export DB_USER
export DB_PASS
export DB_BASE

. $ETCDIR/elasticsearch
export ELASTICSEARCH_ENABLED
export ELASTICSEARCH_HOST
export ELASTICSEARCH_PORT
export ELASTICSEARCH_TIMEOUT
export ELASTICSEARCH_USERNAME
export ELASTICSEARCH_PASSWORD

. $ETCDIR/memcached
export MEMCACHED_ENABLED
export MEMCACHED_HOST
export MEMCACHED_PORT


service haproxy restart

while true; do

    sleep 60
    echo "Starting Pastebin scrapy...."
    python /opt/torscraper/torscraper/spiders/pastebin_scrapy.py
done
