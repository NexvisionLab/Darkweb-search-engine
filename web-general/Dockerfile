FROM python:3.8
MAINTAINER Olivier Bilodeau <obilodeau@gosecure.ca>
# Modified from a Dockerfile by Madison Bahmer <madison.bahmer@istresearch.com>
# Under the MIT license
# https://github.com/istresearch/scrapy-cluster/blob/master/docker/crawler/Dockerfile

# RUN apk update
# RUN apk add --update --no-cache curl py-pip
# RUN apk add python3 python3-dev libffi-dev gcc make musl-dev py-pip mysql-client openssl-dev libxml2-dev libxslt1-dev

# os setup
RUN apt-get update && apt-get -y install \
  python-lxml \
  build-essential \
  libssl-dev \
  libffi-dev \
  python-dev \
  libxml2-dev \
  libxslt1-dev \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/torscraper/web
COPY . /opt/torscraper/web
WORKDIR /opt/torscraper/web


RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade requests

RUN chmod +x /opt/torscraper/web/docker-entrypoint.sh

CMD ["/opt/torscraper/web/docker-entrypoint.sh"]
