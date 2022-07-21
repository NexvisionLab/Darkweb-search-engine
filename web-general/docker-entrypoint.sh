#!/bin/sh

DIR=$( cd "$(dirname "$0")" ; pwd -P )
. /opt/torscraper/scripts/env.sh

# echo "Waiting for $DB_HOST to be ready"
# while ! mysqladmin ping -h $DB_HOST --silent; do
#     # Show some progress
#     echo -n '.';
#     sleep 1;
# done
# echo "$DB_HOST is ready"
# Give it another second.
sleep 1;

/opt/torscraper/scripts/web.sh
