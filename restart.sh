#!/bin/bash

docker-compose down
docker-compose down
chmod 777 -R *
# build 
docker build --tag scraper_surface surface-link-scraper/
docker build --tag scraper_authproxy reverse_proxy/
docker build --tag scraper_crawler ./

docker-compose up -d --build
docker-compose logs -f
