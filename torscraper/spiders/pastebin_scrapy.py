import re
import os
import time as ttime
import json
import urllib
import sys
import hashlib

from datetime import datetime
from elasticsearch import helpers
from elasticsearch import Elasticsearch

from tor_db import *
import email_util

DOMAIN_ID = "0"
DOC_TYPE = "pastebin"
DOC_IDNEX = "hiddenservices"

from elasticsearch import RequestsHttpConnection, serializer, compat, exceptions


class JSONSerializerPython2(serializer.JSONSerializer):
    """Override elasticsearch library serializer to ensure it encodes utf characters during json dump.
    See original at: https://github.com/elastic/elasticsearch-py/blob/master/elasticsearch/serializer.py#L42
    A description of how ensure_ascii encodes unicode characters to ensure they can be sent across the wire
    as ascii can be found here: https://docs.python.org/2/library/json.html#basic-usage
    """

    def dumps(self, data):
        # don't serialize strings
        if isinstance(data, compat.string_types):
            return data
        try:
            return json.dumps(data, default=self.default, ensure_ascii=True)
        except (ValueError, TypeError) as e:
            raise exceptions.SerializationError(data, e)


def is_interesting(data):
    """Determine if data contains any interesting artifacts"""
    return True


@db_session
def update_email_database(addr):
    email = Email.get(address=addr)
    if not email:
        email = Email(address=addr)
    commit()


def main():
    elasticClient = Elasticsearch(
        [os.environ['ELASTICSEARCH_HOST'] + ':' + os.environ['ELASTICSEARCH_PORT']],
        http_auth=(os.environ['ELASTICSEARCH_USERNAME'], os.environ['ELASTICSEARCH_PASSWORD']),
        serializer=JSONSerializerPython2()
    )

    """Scrape all the things"""
    # http://pastebin.com/api_scraping.php
    # http://pastebin.com/api_scrape_item.php?i=UNIQUE_PASTE_KEY
    # http://pastebin.com/api_scrape_item_meta.php?i=UNIQUE_PASTE_KEY
    # api_scraping.php?limit=X (max 500)

    # TODO: KeyboardInterrupt handler
    # TODO: replace urllib/urllib2 with requests

    pastebin_keys = []
    pastebin = ""
    limit = 100  # TODO: CLI setting
    url = "https://scrape.pastebin.com/api_scraping.php"
    values = {'limit': limit}
    url_values = urllib.parse.urlencode(values)

    full_url = url + '?' + url_values

    elasticdata = []

    while True:

        ttime.sleep(60)  # TODO: CLI setting
        # TODO: exit if IP is not whitelisted.
        try:
            data = json.load(urllib.request.urlopen(full_url))
        except Exception as ex:
            print("ex-1:", ex)
            sys.stdout.flush()
            continue

        pastebin_keys = pastebin_keys[:limit]

        for paste in data:

            if paste['key'] in pastebin_keys:
                continue

            pastebin_keys.insert(0, paste['key'])
            # print(paste['key'], paste['date'], paste['scrape_url'], paste['full_url'])
            # TODO: add exception handling
            scrape = urllib.request.urlopen(paste['scrape_url'])
            scrape_data = scrape.read().decode('utf-8')
            if is_interesting(scrape_data):
                document = {}
                document['body'] = scrape_data
                document['body_stripped'] = scrape_data
                document['body_stripped_raw'] = scrape_data
                document['code'] = 200
                document['domain_id'] = DOMAIN_ID
                document['title'] = paste['title']
                document['title_raw'] = paste['title']
                document['domain'] = "pastebin.com"
                document['url'] = paste['full_url']
                document['is_frontpage'] = False
                document['created_at'] = datetime.utcnow()
                document['visited_at'] = datetime.utcnow()
                document['type'] = DOC_TYPE

                elasticdata.append({
                    '_op_type': 'update',
                    '_index': DOC_IDNEX,
                    '_id': paste['full_url'],
                    '_routing': "pastebin.com",
                    'doc': document,
                    'doc_as_upsert': True
                })

                for addr in re.findall(email_util.REGEX, scrape_data):
                    addr = addr.lower()
                    print("found email %s" % addr)
                    sys.stdout.flush()
                    try:
                        update_email_database(addr)
                    except Exception as ex:
                        print("ex-2", ex)
                        sys.stdout.flush()

        try:
            helpers.bulk(elasticClient, elasticdata, index=DOC_IDNEX)
        except Exception as ex:
            print("ex-3:", ex)
            sys.stdout.flush()

        print(str(len(elasticdata)) + ' pastes posted. ' + str(len(data)))        
        sys.stdout.flush()

        elasticdata = []


if __name__ == "__main__":

    while True:
        ttime.sleep(60)
        try:
            main()
        except Exception as ex:
            print("ex-0", ex)
            sys.stdout.flush()
