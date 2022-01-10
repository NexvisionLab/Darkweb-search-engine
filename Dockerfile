FROM python:3.8
MAINTAINER Olivier Bilodeau <obilodeau@gosecure.ca>
# Modified from a Dockerfile by Madison Bahmer <madison.bahmer@istresearch.com>
# Under the MIT license
# https://github.com/istresearch/scrapy-cluster/blob/master/docker/crawler/Dockerfile

# os setup
RUN apt-get update && apt-get -y install \
  lynx \
  python-lxml \
  build-essential \
  libssl-dev \
  libffi-dev \
  python-dev \
  libxml2-dev \
  libxslt1-dev \
  haproxy \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/torscraper/
WORKDIR /opt/torscraper

# install requirements
COPY requirements.txt /opt/torscraper
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade requests

# download spacy models
RUN python -m spacy download ca_core_news_md
RUN python -m spacy download zh_core_web_md
RUN python -m spacy download da_core_news_md
RUN python -m spacy download nl_core_news_md
RUN python -m spacy download en_core_web_lg
RUN python -m spacy download fr_core_news_md
RUN python -m spacy download de_core_news_md
RUN python -m spacy download el_core_news_md
RUN python -m spacy download it_core_news_md
RUN python -m spacy download ja_core_news_md
RUN python -m spacy download lt_core_news_md
RUN python -m spacy download mk_core_news_md
RUN python -m spacy download nb_core_news_md
RUN python -m spacy download pl_core_news_md
RUN python -m spacy download pt_core_news_md
RUN python -m spacy download ro_core_news_md
RUN python -m spacy download ru_core_news_md
RUN python -m spacy download es_core_news_md

# move codebase over
COPY . /opt/torscraper

# move haproxy config to haproxy directory
COPY init/haproxy.cfg /etc/haproxy/haproxy.cfg
#Need to automate the service start when boot


## override settings via localsettings.py
#COPY docker/crawler/settings.py /usr/src/app/crawling/localsettings.py
#
## copy testing script into container
#COPY docker/run_docker_tests.sh /usr/src/app/run_docker_tests.sh
#
## set up environment variables
#
## run the spider
#CMD ["scrapy", "runspider", "crawling/spiders/link_spider.py"]
# CMD ["/opt/torscraper/scripts/docker_haproxy_harvest_scrape.sh"]