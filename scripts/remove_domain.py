#!/usr/bin/env python
from pony.orm import *
from datetime import *
from tor_db import *
from tor_elasticsearch import  *
import sys

@db_session(optimistic=False)
def remove_domain_all():

    host   = sys.argv[1]

    while True:
        try:
            res = elasticsearch_delete_domain(host)
            print(str(res))
            break
        except Exception as ex:
            print("0-" + str(ex))

    while True:
        domain = Domain.get(host=host)
        if domain is None:
            break
        page_list = Page.select(lambda p: p.domain == domain)

        while page_list and len(page_list) != 0:
            count = 0
            # for page in page_list:
            #     try:
            #         page.links_from.clear()
            #     except Exception as ex:
            #         print("Error while removing page link_from: " + str(ex))
            #     try:
            #         page.links_to.clear()
            #     except Exception as ex:
            #         print("Error while removing page links_to: " + str(ex))
            #     try:
            #         page.bitcoin_addresses.clear()
            #     except Exception as ex:
            #         print("Error while removing page bitcoin_addresses: " + str(ex))
            #     count = count + 1
            #     if count % 50 == 0:
            #         print(f"cleaning page links for f{domain}, {count}/{len(page_list)}")
            #         sys.stdout.flush()
                
            try:
                Page.select(lambda p: p.domain == domain).delete(bulk=True)
                commit()
                page_list = Page.select(lambda p: p.domain == domain)
            except Exception as ex:
                print("error while deleting pages " + host)
                print(str(ex))
                sys.stdout.flush()
        
        break
        # try:
        #     domain.delete()
        #     commit()
        # except Exception as ex:
        #     print("error while deleting domain " + host)
        #     print(str(ex))
        #     sys.stdout.flush()

    print("removing domain finished " + host)
    sys.stdout.flush()

remove_domain_all()
sys.exit(0)