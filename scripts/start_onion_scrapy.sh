#!/bin/bash

run_scrapy(){
  while true;
  do
    /opt/torscraper/scripts/scrape.sh
  done
}

#service haproxy restart
#echo "========scraper harvest start=========="
#/opt/torscraper/scripts/harvest.sh
#echo "=========scraper harvest end push_list start=========="
#/opt/torscraper/scripts/push_list.sh /opt/torscraper/onions_list/onions.txt
#echo "==========scraper push_list end scrape start==========================="

while true; do
    service haproxy restart
    for i in {1..1}
    do
        sleep 20
        run_scrapy &
    done
    wait
done
echo "==========scraper scrap end=================="