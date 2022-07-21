#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
START_URLS=$1

. $DIR/env.sh
(
cd $BASEDIR
scrapy crawl tor -a is_grab=yes -a grab_url="$START_URLS" -a test=yes 
)

