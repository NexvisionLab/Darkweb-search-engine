FROM python:3.8

# os setup
RUN apt-get update && apt-get -y install \
  python3-dev \
  python3-lxml \
  build-essential \
  libssl-dev \
  libffi-dev \
  libxml2-dev \
  libxslt1-dev \
  && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/torscraper/web

WORKDIR /opt/torscraper/web

COPY requirements.txt /opt/torscraper/web/requirements.txt

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade requests

RUN python -m spacy download en_core_web_lg

COPY . /opt/torscraper/web/

RUN chmod +x /opt/torscraper/web/docker-entrypoint.sh

CMD ["/opt/torscraper/web/docker-entrypoint.sh"]
