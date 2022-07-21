#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
. $DIR/env.sh

count=0

while IFS= read -r line
do
    host=$( echo -n "$line" )
    count=$(( $count + 1 ))
    URL=$host
    if echo $host | grep -q -v -E "^http:"; then
        URL=http://$host
    fi;
    echo ""
    echo "#####################################################################"
    echo "Pushing $count : $URL"
    echo "#####################################################################"
    echo ""
    scrapy crawl tor -a test=yes -a passed_url=$URL
done < "$1"

echo "crawling finished: $1"