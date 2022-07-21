#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
. $DIR/env.sh
curl --socks5-hostname $SOCKS_PROXY --connect-timeout 30 $1| grep -E -o '([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}'
