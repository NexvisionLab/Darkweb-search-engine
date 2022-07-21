FROM python:3.6
ENV PYTHONUNBUFFERED 1

# App setup
ADD . /work
WORKDIR /work

# os setup
RUN apt-get update && apt-get -y install \
  python3-lxml \
  build-essential \
  libssl-dev \
  libffi-dev \
  python-dev \
  libxml2-dev \
  libxslt1-dev \
  haproxy \
  && rm -rf /var/lib/apt/lists/*

COPY ./haproxy.cfg /etc/haproxy/haproxy.cfg

# COPY ./entrypoint.sh /
ENTRYPOINT ["./entrypoint.sh"]
# CMD ["python manage.py runserver 0.0.0.0:8000"]