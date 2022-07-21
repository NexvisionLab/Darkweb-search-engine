#!/bin/sh
echo "running, 0" > /tmp/status

DIR=$( cd "$(dirname "$0")" ; pwd -P )
SITE_INFO=$1
service haproxy restart
. $DIR/env.sh
(
cd $BASEDIR
scrapy crawl tor -a site_info="$SITE_INFO" -a test=no -a  is_proxy=yes
)

