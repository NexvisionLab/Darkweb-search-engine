#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
. $DIR/env.sh
cd $BASEDIR

LOGIN_INFO=$1

scrapy crawl tor -a login_info="$LOGIN_INFO" -a test=no -a  login=yes

