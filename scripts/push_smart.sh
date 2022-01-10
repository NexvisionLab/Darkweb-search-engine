#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
. $DIR/env.sh
cd $BASEDIR
URL=http://$1/
case $1 in
  "http"*) URL=$1 ;;
esac

DOMAIN=$( echo "$URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||' )

unset http_proxy
unset https_proxy
case $DOMAIN in
  *".onion") . $DIR/env.sh ;;
esac

echo "Pushing $URL"
scrapy crawl tor -a passed_url=$URL -a request_delay=$2 -a test=no
