import scrapy
import urllib.parse
import re
import os
from scrapy.http import FormRequest
from collections import *
from pony.orm import *
from datetime import *
from tor_db import *
from tor_elasticsearch import *
from os import path
import json
import random
import tor_text
import string
import random
import timeout_decorator
import bitcoin
import email_util
import interesting_paths
import tor_text
import time
import sys
import json
import shutil
import base64
import requests
import collections

from urllib.parse import urlparse

SUBDOMAIN_PENALTY    = 6 * 60
NORMAL_RAND_RANGE    = 2 * 60
SUBDOMAIN_RAND_RANGE = 6 * 60
MAX_DEAD_IN_A_ROW    = 30
PENALTY_BASE         = 1.5

script_cnt = 0

from scrapy.exceptions import IgnoreRequest

url_regex = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)


def maybe_add_scheme(onion):
    o = onion.strip()
    if not re.match(r"^(http|https)://", o):
        o = ("http://%s/" % o)
    return o


@db_session
def domain_urls_down():
    urls = []
    now = datetime.now()
    event_horizon = now - timedelta(days=30)
    n_items = count(d for d in Domain if d.last_alive > event_horizon and d.is_up == False)
    for domain in Domain.select(lambda d: d.is_up == False and d.last_alive > event_horizon).random(n_items):
        urls.append(domain.index_url())
    return urls


@db_session
def domain_urls_resurrect():
    urls = []
    now = datetime.now()
    event_horizon = now - timedelta(days=30)
    n_items = count(d for d in Domain if d.last_alive < event_horizon and d.is_up == False)
    for domain in Domain.select(lambda d: d.is_up == False and d.last_alive < event_horizon).random(n_items):
        urls.append(domain.index_url())
    return urls


@db_session
def domain_urls():
    urls = []
    for domain in Domain.select():
        urls.append(domain.index_url())
    return urls


@db_session
def domain_urls_recent_no_crap():
    urls = []
    now = datetime.now()
    event_horizon = now - timedelta(days=30)
    n_items = count(d for d in Domain if d.is_up == True and d.is_crap == False)
    for domain in Domain.select(lambda d: d.is_up == True and d.is_crap == False).random(n_items):
        urls.append(domain.index_url())
    return urls


### rider added
@db_session
def domain_urls_last_check():
    urls = []
    n_items = count(d for d in Domain)
    if n_items > 1:
        n_items = 1
    for domain in Domain.select().order_by(Domain.visited_at)[:n_items]:
        urls.append(domain.index_url())
        domain.visited_at = datetime.now()
    return urls
####


@db_session
def domain_urls_recent():
    urls = []
    now = datetime.now()
    event_horizon = now - timedelta(days=30)
    n_items = count(d for d in Domain if d.last_alive > event_horizon)
    for domain in Domain.select(lambda d: d.last_alive > event_horizon).random(n_items):
        urls.append(domain.index_url())
    return urls


@db_session
def domain_urls_next_scheduled():
    urls = []
    now = datetime.now()

    for domain in Domain.select(lambda d: now > d.next_scheduled_check).order_by(Domain.visited_at):
        urls.append(domain.index_url())
    return urls


@db_session
def domain_urls_next_scheduled_old():
    urls = []
    now = datetime.now()
    event_horizon = now - timedelta(days=30)
    for domain in Domain.select(lambda d: now > d.next_scheduled_check and d.last_alive > event_horizon).order_by(Domain.visited_at):
        urls.append(domain.index_url())
    return urls


@db_session
def get_allowed_domain():
    allowed = AllowedDomain.select()
    res = ['onion']
    for domain in allowed:
        if domain.domain not in res:
            res.append(domain.domain)
    return res


@db_session
def get_blocked_domain():
    blocked = BlockedDomain.select()
    res = []
    for domain in blocked:
        if domain.domain not in res:
            res.append(domain.domain)
    return res


def json_convert(data):
    if isinstance(data, str):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(json_convert, data.items()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(json_convert, data))
    else:
        return data


class TorSpider(scrapy.Spider):
    name = "tor"
    allowed_domains = ['onion']
    handle_httpstatus_list = [429, 404, 403, 401, 503, 500, 504, 502, 206]
    handle_httpstatus_all = True
    start_urls = domain_urls_last_check()
    if len(start_urls) == 0:
        start_urls = [
            'http://gxamjbnu7uknahng.onion/',
            'http://mijpsrtgf54l7um6.onion/',
            'http://dirnxxdraygbifgc.onion/',
            'http://torlinkbgs6aabns.onion/'
        ]

    custom_settings = {
        'DOWNLOAD_MAXSIZE': (1024 * 1024) * 2,
        'BIG_DOWNLOAD_MAXSIZE': (1024 * 1024) * 4,
        'ALLOW_BIG_DOWNLOAD': [
            '7cbqhjnlkivmigxf.onion'
        ],
        'INJECT_RANGE_HEADER': True,
        'ROBOTSTXT_OBEY': False,
	    'CONCURRENT_REQUESTS' : 1024,
        'MEMUSAGE_LIMIT_MB' : 4096,
        'REACTOR_THREADPOOL_MAXSIZE' : 32,
        'CONCURRENT_REQUESTS_PER_DOMAIN' : 8,
        'DEPTH_PRIORITY' : 1,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
        'MAX_PAGES_PER_DOMAIN': 100000000,
        'URLLENGTH_LIMIT': 8332,
        'HTTPERROR_ALLOWED_CODES': handle_httpstatus_list,
        'RETRY_HTTP_CODES': [],
        'DOWNLOADER_MIDDLEWARES': {
            # 'torscraper.middlewares.FilterDomainByPageLimitMiddleware': 551,
            # 'torscraper.middlewares.FilterTooManySubdomainsMiddleware': 550,
            # 'torscraper.middlewares.FilterDeadDomainMiddleware' : 556,
            # 'torscraper.middlewares.AllowBigDownloadMiddleware': 557,
            # 'torscraper.middlewares.FilterNotScheduledMiddleware': 558,
        },
        'SPIDER_MIDDLEWARES': {
            'torscraper.middlewares.InjectRangeHeaderMiddleware': 543,
        },
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36',
    }
    spider_exclude = [
        'blockchainbdgpzk.onion',
        'ypqmhx5z3q5o6beg.onion',
        'jld3zkuo4b5mbios.onion',
    ]

    

    def __init__(self, *args, **kwargs):
        super(TorSpider, self).__init__(*args, **kwargs)
        # set download_delay        
        if hasattr(self, "request_delay"):
            self.download_delay = float(int(self.request_delay))
        #
        if hasattr(self, "is_proxy") and self.is_proxy == "yes":
            self.site_info = json_convert(json.loads(self.site_info.replace("'", '"')))
            self.start_urls = [self.site_info['proxy_endpoint']]
            if "blocked_urls" not in self.site_info:
                self.site_info["blocked_urls"] = []
            self.download_delay = float(int(self.site_info["request_interval"])) / 1000.0
        elif hasattr(self, "is_grab") and self.is_grab == "yes": # for search engine scraping
            self.start_urls = [self.grab_url]
            with open('/opt/torscraper/torscraper/spiders/words.txt') as filestream:
                filecontent = filestream.readlines()
            self.search_words = [x.strip() for x in filecontent]
            self.found_onions = []
            self.download_delay = 120.0 # download delay for search engine
        elif hasattr(self, "passed_url"):
            self.start_urls = [self.passed_url]
        elif hasattr(self, "load_links") and self.load_links == "downonly":
            self.start_urls = domain_urls_down()
        elif hasattr(self, "load_links") and self.load_links == "resurrect":
            self.start_urls = domain_urls_resurrect()
        elif hasattr(self, "load_links"):
            self.start_urls = [maybe_add_scheme(line) for line in open(self.load_links)]
        elif hasattr(self, "test") and self.test == "yes":
            if not hasattr(self, "load_links"):
                if hasattr(self, "alive") and self.alive == "yes":
                    self.start_urls = domain_urls_next_scheduled_old()
                else:
                    self.start_urls = domain_urls_next_scheduled()
        else:
            self.start_urls = domain_urls_last_check()

        self.allowed_domains = get_allowed_domain()
        self.spider_exclude = get_blocked_domain()

        self.start_domains = []
        for start_url in self.start_urls:
            #### for marketplaces ####
            parsed_url = urlparse(start_url)
            if parsed_url.hostname not in self.allowed_domains:
                self.allowed_domains.append(parsed_url.hostname)
            if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                start_url = start_url.replace(self.site_info['proxy_endpoint'], self.site_info['target_endpoint'])
            #####
            parsed_url = urlparse(start_url)
            if parsed_url.hostname not in self.start_domains:
                self.start_domains.append(parsed_url.hostname)

        if hasattr(self, "is_grab") and self.is_grab == "yes":  # for search engine scraping allow start domain even it is not allowed by default
            self.allowed_domains = self.allowed_domains + self.start_domains


        print("\n\n\nstart urls/domains")
        print("start_urls:", self.start_urls)
        print("start_domains:", self.start_domains)
        print("allowed_domains:", self.allowed_domains)
        try:
            print("download_delay:", self.download_delay)
        except:
            pass
        # print(self.spider_exclude)
        print("\n\n\n")
        sys.stdout.flush()



    @db_session
    def update_page_info(self, url, title, code, is_frontpage=False, size=0):
        
        print("update_page_info....", url)
        sys.stdout.flush()

        if not Domain.is_onion_url(url):
            return False

        if title == "ERROR: The requested URL could not be retrieved":
            return False

        failed_codes = [666, 503, 504, 502]
        responded_codes = [200, 206, 403, 500, 401, 301, 302, 304, 400]
        if (hasattr(self, "only_success") and self.only_success == "yes" and
                code not in responded_codes):
            return False

        if not title:
            title = ''
        # limit title if long
        if len(title) > 250:
            title = title[0:250]
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        if host == "zlal32teyptf4tvi.onion":
            return False

        # remove out domain
        out_flag = True
        for temp_domain in self.allowed_domains:
            if host.endswith(temp_domain):
                out_flag = False
                break
        if out_flag:
            return False
        ###################

        port = parsed_url.port
        ssl = parsed_url.scheme == "https://"
        path = '/' if parsed_url.path == '' else parsed_url.path
        # is_up = not code in failed_codes
        is_up = (code >= 200 and code < 300)
        if not port:
            if ssl:
                port = 443
            else:
                port = 80

        now = datetime.now()

        domain = Domain.get(host=host, port=port, ssl=ssl)
        is_crap = False
        if not domain:
            if is_up:
                last_alive = now
                # rider added : to add only alive domain
                # else:
                #     last_alive = NEVER
                #     title=''
                domain = Domain(host=host, port=port, ssl=ssl, is_up=is_up, last_alive=last_alive,
                                created_at=now, next_scheduled_check=(now + timedelta(hours=1)), visited_at=NEVER,
                                title=title)
                self.log("created domain %s" % host)
            else:
                return False
        else:
            if is_up:
                domain.is_up = is_up
            elif is_frontpage:
                if host in self.start_domains:
                    domain.is_up = is_up
            if host in self.start_domains and not (hasattr(self, "test") and self.test == "yes"):
                domain.visited_at = now
            if is_up:

                if domain.last_alive == NEVER:
                    domain.created_at = now

                domain.last_alive = now

                if is_frontpage:
                    if not (domain.title != '' and title == ''):
                        domain.title = title
            else:
                print("\n\n\n\n\n##################\nDOMAIN DEADED " + domain.host + " " + str(code) + "\n\n\n\n")

        page = Page.get(url=url)
        if not page:
            page = Page(url=url, title=title, code=code, created_at=now, visited_at=now, domain=domain,
                        is_frontpage=is_frontpage, size=size)
        else:
            if is_up:
                page.title = title
            page.code = code
            page.visited_at = now
            page.size = size
            if not page.is_frontpage and is_frontpage:
                page.is_frontpage = is_frontpage
        commit()
        return page

    
    @timeout_decorator.timeout(5)
    @db_session
    def extract_other(self, page, body):
        self.log("extract_other")
        # page.emails.clear()
        self.log("find_emails")
        for addr in re.findall(email_util.REGEX, body.decode('utf-8')):
            addr = addr.lower()
            self.log("found email %s" % addr)
            email = Email.get(address=addr)
            if not email:
                email = Email(address=addr)
            # page.emails.add(email)
            # store email in elasticsearch
            if is_elasticsearch_enabled():
                emailDoc = EmailDocType.from_obj(addr)
                emailDoc.save()

        # page.bitcoin_addresses.clear()
        self.log("find_bitcoin")
        for addr in re.findall(bitcoin.REGEX, body.decode('utf-8')):
            if not bitcoin.is_valid(addr):
                self.log("found address, invalid %s" % addr)
                continue
            self.log("found address, valid %s" % addr)
            bitcoin_addr = BitcoinAddress.get(address=addr)
            if not bitcoin_addr:
                bitcoin_addr = BitcoinAddress(address=addr)
            bitcoin_addr.page_url = page.url
            page.bitcoin_addresses.add(bitcoin_addr)


    @db_session
    def description_json(self, response):
        #### for marketplaces ####
        if hasattr(self, "is_proxy") and self.is_proxy == "yes":
            response = response.replace(url=response.url.replace(self.site_info['proxy_endpoint'], self.site_info['target_endpoint']))
        #####
        domain = Domain.find_by_url(response.url)
        if not domain or response.status in [502, 503]:
            return None
        if response.status in [200, 206]:
            domain.description_json = json.loads(response.body)
        else:
            domain.description_json = {}



    @db_session
    def useful_404_detection(self, response):
        #### for marketplaces ####
        if hasattr(self, "is_proxy") and self.is_proxy == "yes":
            response = response.replace(url=response.url.replace(self.site_info['proxy_endpoint'], self.site_info['target_endpoint']))
        #####
        domain = Domain.find_by_url(response.url)
        is_php = re.match(r".*\.php$", response.url)
        is_dir = re.match(r".*/$", response.url)
        if not domain or response.status in [502, 503]:
            return None
        if response.status == 404:
            if is_php:
                domain.useful_404_php = True
            elif is_dir:
                domain.useful_404_dir = True
            else:
                domain.useful_404     = True
        else:
            if is_php:
                domain.useful_404_php = False
            elif is_dir:
                domain.useful_404_dir = False
            else:
                domain.useful_404     = False
    
        domain.useful_404_scanned_at = datetime.now()
        return None



    @db_session
    def parse(self, response, recent_alive_check=False):

        global script_cnt
        print("parsing...", script_cnt, response.url)
        sys.stdout.flush()
        
        #### for marketplaces ####
        if hasattr(self, "is_proxy") and self.is_proxy == "yes" and self.site_info['proxy_endpoint'] in response.url:
            # check if login page
            if 'check_string' in self.site_info:
                is_login_page = False
                valid_checkwords = None
                for checkwords in self.site_info['check_string']:
                    is_login_page = True
                    for checkword in checkwords:
                        if checkword not in response.body.decode('utf-8'):
                            is_login_page = False
                            break
                    if is_login_page:
                        is_login_page = True
                        valid_checkwords = checkwords
                        break
                if is_login_page == True:
                    print("session expired...", response.url, valid_checkwords)
                    sys.stdout.flush()
                    os.system('echo "session_expired, {}" > /tmp/status'.format(script_cnt))
                    time.sleep(120)
                    yield scrapy.Request(response.url, callback=self.parse, dont_filter=True, priority=100000000)
                    return
            response = response.replace(url=response.url.replace(self.site_info['proxy_endpoint'], self.site_info['target_endpoint']))
            response = response.replace(body=response.body.replace(str.encode(self.site_info['proxy_endpoint']), str.encode(self.site_info['target_endpoint'])))
        #####

        parsed_url = urlparse(response.url)
        host = parsed_url.hostname    

        if hasattr(self, "is_grab") and self.is_grab == "yes" and host in self.start_domains:  # for search engine scraping call specific parsing function for start domains
            # priority = 0
            # if 'priority' in response.meta:
            #     priority = response.meta['priority']
            for new_onion in re.findall('[\w\-\.]+\.onion', response.body.decode('utf-8')):
                if new_onion in self.found_onions:
                    continue
                self.found_onions.append(new_onion)
                print("onion found...", new_onion, len(self.found_onions))
                sys.stdout.flush()
                request_url = "http://{}".format(new_onion)
                yield scrapy.Request(request_url, callback=self.parse, priority=500, meta={'priority': 500})
            for url in response.xpath('//a/@href').extract():
                request_url = response.urljoin(url)
                yield scrapy.Request(request_url, callback=self.parse, priority=300, meta={'priority': 300})
            if 'SEARCHWORD' in self.start_urls[0]:
                searchword = self.search_words.pop(0)
                request_url = self.start_urls[0].replace('SEARCHWORD', searchword)
                print(len(self.found_onions), len(self.search_words), "- making search request....", '"{}"'.format(searchword), request_url)
                sys.stdout.flush()
                yield scrapy.Request(request_url, callback=self.parse, dont_filter=True, priority=1, meta={'priority': 100})
                yield scrapy.Request(request_url, callback=self.parse, dont_filter=True, priority=1, meta={'priority': 400})
                yield scrapy.Request(request_url, callback=self.parse, dont_filter=True, priority=1, meta={'priority': 700})
            return

        if not (response.status >= 200 and response.status < 300):
            print("Error page detected " + str(response.status) + " " + str(response.url))
            sys.stdout.flush()
            return
        
        script_cnt += 1

        # for marketplace
        if hasattr(self, "is_proxy") and self.is_proxy == "yes":
            os.system('echo "running, {}" > /tmp/status'.format(script_cnt))

        MAX_PARSE_SIZE_KB = 1000
        title = ''
        try:
            title = response.css('title::text').extract_first()
        except AttributeError:
            pass
        
        if host != "zlal32teyptf4tvi.onion" and host not in self.spider_exclude:
            self.log('Got %s (%s)' % (response.url, title))
            is_frontpage = Page.is_frontpage_request(response.request)
            size = len(response.body)

            page = self.update_page_info(response.url, title, response.status, is_frontpage, size)
            if not page:
                commit()
                return

            # extra headers

            got_server_response = page.got_server_response()
            if got_server_response and response.headers.get("Server"):
                page.domain.server = tor_text.utf8_conv(response.headers.get("Server"))
            if got_server_response and response.headers.get("X-Powered-By"):
                page.domain.powered_by = tor_text.utf8_conv(response.headers.get("X-Powered-By"))
            if got_server_response and response.headers.get("Powered-By"):
                page.domain.powered_by = tor_text.utf8_conv(response.headers.get("Powered-By"))
            domain = page.domain

            # don't check subdomains that often

            penalty = 0
            rng = NORMAL_RAND_RANGE
            if domain.is_subdomain:
                penalty = SUBDOMAIN_PENALTY
                rng     = SUBDOMAIN_RAND_RANGE

            if domain.is_up:
                domain.dead_in_a_row = 0

                domain.next_scheduled_check = datetime.now() + timedelta(minutes=penalty + random.randint(60, 60 + rng))
            else:
                yield_later = None
                # check newly dead domains immediately
                if domain.dead_in_a_row == 0 and not recent_alive_check:
                    self.log('checking the freshly dead (%s) for movement' % domain.host)
                    r = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(7, 12)))
                    test_url = domain.index_url() + r
                    
                    if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                        yield_later = scrapy.Request(test_url.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=lambda r: self.parse(r, recent_alive_check=True))
                    else:
                        yield_later = scrapy.Request(test_url, callback=lambda r: self.parse(r, recent_alive_check=True))
                if not recent_alive_check:
                    domain.dead_in_a_row += 1
                    if domain.dead_in_a_row > MAX_DEAD_IN_A_ROW:
                        domain.dead_in_a_row = MAX_DEAD_IN_A_ROW
                    domain.next_scheduled_check = (datetime.now() + 
                        timedelta(minutes = penalty + random.randint(60, 60 + rng) * (PENALTY_BASE ** domain.dead_in_a_row)))

                commit()
                if yield_later:
                    yield yield_later

            is_text = False
            content_type = response.headers.get("Content-Type").decode('utf-8')
            if got_server_response and content_type and re.match('^text/', content_type.strip()):
                is_text = True

            # elasticsearch
            if is_elasticsearch_enabled() and is_text:
                self.log('Inserting %s page into elasticsearch' % response.url)
                if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                    pg = PageDocType.from_obj(page, response.body, True)
                else:
                    pg = PageDocType.from_obj(page, response.body)
                pg.save()
            commit()
            # add some randomness to the check

            path_event_horizon = datetime.now() - timedelta(days=14 + random.randint(0, 14))

            # interesting paths

            if domain.is_up and domain.path_scanned_at < path_event_horizon:
                domain.path_scanned_at = datetime.now()
                commit()
                for url in interesting_paths.construct_urls(domain):
                    if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                        yield scrapy.Request(url.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.parse)
                    else:
                        yield scrapy.Request(url, callback=self.parse)

            # /description.json

            if domain.is_up and domain.description_json_at < path_event_horizon:
                domain.description_json_at = datetime.now()
                commit()
                if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                    yield scrapy.Request(domain.construct_url("/description.json").replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.description_json)
                else:
                    yield scrapy.Request(domain.construct_url("/description.json"), callback=self.description_json)

            # language detection

            if domain.is_up and is_frontpage and (response.status == 200 or response.status == 206):
                domain.detect_language(tor_text.strip_html(response.body))
                commit()

            # 404 detections

            if domain.is_up and is_frontpage and domain.useful_404_scanned_at < (datetime.now() - timedelta(weeks=2)):
                
                # standard

                r = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(7, 12)))
                url = domain.index_url() + r
                if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                    yield scrapy.Request(url.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.useful_404_detection)
                else:
                    yield scrapy.Request(url, callback=self.useful_404_detection)

                # php

                r = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(7, 12)))
                url = domain.index_url() + r + ".php"
                if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                    yield scrapy.Request(url.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.useful_404_detection)
                else:
                    yield scrapy.Request(url, callback=self.useful_404_detection)

                # dir

                r = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(7, 12)))
                url = domain.index_url() + r + "/"
                if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                    yield scrapy.Request(url.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.useful_404_detection)
                else:
                    yield scrapy.Request(url, callback=self.useful_404_detection)

            link_to_list = []            
            self.log("Finding links...")

            if (not hasattr(self, "test") or self.test != "yes") and not host in self.spider_exclude and host in self.start_domains:
                for url in response.xpath('//a/@href').extract():
                    fullurl = response.urljoin(url)
                    # remove out domain
                    parsed_fullurl = urlparse(fullurl)
                    temp_host = parsed_fullurl.hostname
                    if temp_host is None:
                        continue
                    out_flag = True
                    for temp_domain in self.allowed_domains:
                        if temp_host.endswith(temp_domain):
                            out_flag = False
                            break
                    if out_flag:
                        continue
                    ###################

                    if hasattr(self, "is_proxy") and self.is_proxy == "yes":
                        if self.is_blocked(fullurl) is not True:
                            yield scrapy.Request(fullurl.replace(self.site_info['target_endpoint'], self.site_info['proxy_endpoint']), callback=self.parse)
                        # add dummy request for login check
                        if random.random() < 0.1:
                            yield scrapy.Request(self.start_urls[0], callback=self.parse, dont_filter=True)
                    else:
                        yield scrapy.Request(fullurl, callback=self.parse)
                    if got_server_response and Domain.is_onion_url(fullurl):
                        try:
                            parsed_link = urlparse(fullurl)
                        except:
                            continue
                        link_host = parsed_link.hostname
                        if host != link_host:
                            link_to_list.append(fullurl)

                self.log("link_to_list %s" % link_to_list)
                
                # rider added 2020-11-7 try to find additional domains
                for new_onion in re.findall('[\w\-\.]+\.onion', response.body.decode('utf-8')):
                    request_url = "http://{}".format(new_onion)
                    yield scrapy.Request(request_url, callback=self.parse)
                ###

                if page.got_server_response():
                    small_body = response.body[:(1024 * MAX_PARSE_SIZE_KB)]
                    # page.links_to.clear()
                    for url in link_to_list:
                        link_to = Page.find_stub_by_url(url)
                        # if link_to != None:
                        #     page.links_to.add(link_to)

                    try:
                        self.extract_other(page, small_body)
                    except timeout_decorator.TimeoutError:
                        pass

                    commit()
        else:
            print("Error... blocked url:", response.url)


    def process_exception(self, response, exception, spider):
        #### for marketplaces ####
        if hasattr(self, "is_proxy") and self.is_proxy == "yes":
            response = response.replace(url=response.url.replace(self.site_info['proxy_endpoint'], self.site_info['target_endpoint']))
        #####
        if response.url in self.start_urls:
            self.update_page_info(response.url, None, 666, is_frontpage=True)
        return


    def is_blocked(self, page_url):
        for blocked_url in self.site_info["blocked_urls"]:
            if page_url.startswith(blocked_url):
                return True
        return False



