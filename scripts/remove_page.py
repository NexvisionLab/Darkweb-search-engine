#!/usr/bin/env python
from pony.orm import *
from datetime import *
from tor_db import *
from tor_elasticsearch import  *
import sys

@db_session(optimistic=False)
def remove_page_all():

    page_url = sys.argv[1]

    while True:
        try:
            res = elasticsearch_delete_page(page_url)
            print(str(res))
            break
        except Exception as ex:
            print("0-" + str(ex))

    while True:
        page = Page.get(url=page_url)
        if page is None:
            break
        try:
            # page.links_from.clear()
            # page.links_to.clear()
            page.bitcoin_addresses.clear()
            page.delete()
            commit()
        except Exception as ex:
            print("error while deleting page " + page_url)
            print(str(ex))
            sys.stdout.flush()

    print("removing page finished " + page_url)
    sys.stdout.flush()

remove_page_all()
sys.exit(0)