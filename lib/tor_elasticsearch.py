import os
from datetime import *
from htmldate import find_date
from langdetect import detect_langs
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Document, Date, Nested, Boolean, MetaField, Keyword
from elasticsearch_dsl import analyzer, Text, Integer, Float, token_filter
from elasticsearch import serializer, compat, exceptions
from elasticsearch_dsl import Search
from elasticsearch_dsl import Q
from elasticsearch_dsl import Index
import re
import sys
import hashlib
import logging
import traceback

import tor_text

# load spacy
import spacy

spacyNLP = {}
try:
    spacyNLP = {
        # 'ca': spacy.load('ca_core_news_md'),
        # 'zh-cn': spacy.load('zh_core_web_md'),
        # 'da': spacy.load('da_core_news_md'),
        # 'nl': spacy.load('nl_core_news_md'),
        'en': spacy.load('en_core_web_lg'),
        # 'fr': spacy.load('fr_core_news_md'),
        'de': spacy.load('de_core_news_md'),
        # 'el': spacy.load('el_core_news_md'),
        # 'it': spacy.load('it_core_news_md'),
        # 'ja': spacy.load('ja_core_news_md'),
        # 'lt': spacy.load('lt_core_news_md'),
        # 'mk': spacy.load('mk_core_news_md'),
        # 'nb': spacy.load('nb_core_news_md'),
        # 'pl': spacy.load('pl_core_news_md'),
        # 'pt': spacy.load('pt_core_news_md'),
        # 'ro': spacy.load('ro_core_news_md'),
        'ru': spacy.load('ru_core_news_md'),
        # 'es': spacy.load('es_core_news_md'),
    }
except Exception as ex: 
    print("Cannot import language library.")
    pass


NEVER = datetime.fromtimestamp(0)

try:
    import simplejson as json
except ImportError:
    import json


from goose3 import Goose
gooseParser = Goose({
    'http_proxies': {
        'http':   'http://127.0.0.1:3128',
        'https':  'https://127.0.0.1:3128',
        'ftp':    'ftp://127.0.0.1:3128',
    }
})                      


class JSONSerializerPython2(serializer.JSONSerializer):
    """Override elasticsearch library serializer to ensure it encodes utf characters during json dump.
    See original at: https://github.com/elastic/elasticsearch-py/blob/master/elasticsearch/serializer.py#L42
    A description of how ensure_ascii encodes unicode characters to ensure they can be sent across the wire
    as ascii can be found here: https://docs.python.org/2/library/json.html#basic-usage
    """
    def dumps(self, data_org):
        # don't serialize strings
        data = {}
        for key, value in data_org.items():
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            data[key] = value
        if isinstance(data, compat.string_types):
            return data
        try:
            return json.dumps(data, default=self.default, ensure_ascii=True)
        except (ValueError, TypeError) as e:
            raise exceptions.SerializationError(data, e)


def elasticsearch_retrieve_page_by_id(page_id):
    query = Search().filter(Q("term", nid=int(page_id)))[:1]
    result = query.execute()
    if result.hits.total == 0:
        return None
    return result.hits[0]


def elasticsearch_delete_old():
    _from = NEVER
    _to   = datetime.now() - timedelta(days=30)
    query = Search().filter(Q("range", visited_at={'from': _from, 'to': _to}))
    result = query.delete()


# rider added
def elasticsearch_delete_domain(domain_address):
    query = Search(index='hiddenservices').filter(Q("term", domain=domain_address))
    result = query.delete()
    return result

def elasticsearch_delete_page(page_url):
    query = Search(index='hiddenservices').filter(Q("term", url=page_url))
    result = query.delete()
    return result
#############

def elasticsearch_pages(context, sort, page):
    result_limit = int(os.environ['RESULT_LIMIT'])
    max_result_limit = int(os.environ['MAX_RESULT_LIMIT'])
    start = (page - 1) * result_limit
    end   = start + result_limit
    # domain_query = Q("term", is_banned=False)
    # if context["is_up"]:
    #     domain_query = domain_query & Q("term", is_up=True)
    # if not context["show_fh_default"]:
    #     domain_query = domain_query & Q("term", is_crap=False)
    # if not context["show_subdomains"]:
    #     domain_query = domain_query & Q("term", is_subdomain=False)
    # if context["rep"] == "genuine":
    #     domain_query = domain_query & Q("term", is_genuine=True)
    # if context["rep"] == "fake":
    #     domain_query = domain_query & Q("term", is_fake=True)

    limit = max_result_limit if context["more"] else result_limit

    # has_parent_query = Q("has_parent", type="domain", query=domain_query)
    if context['phrase']:
        # query = Search().filter(has_parent_query).query(Q("match_phrase", body_stripped=context['search']))
        query = Search().from_dict({
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": context['search']}},
                        {"regexp": {"domain": ".*.onion"}},
                        {"term": {"type": "page"}}
                    ]
                }
            }})
    else:
        # query = Search().filter(has_parent_query).query(Q("match", body_stripped=context['search']))
        query = Search().from_dict({
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title": context['search']}},
                        {"regexp": {"domain": ".*.onion"}},
                        {"term": {"type": "page"}}
                    ]
                }
            }})

    query = query.highlight_options(order='score', encoder='html').highlight('body_stripped')[start:end]
    query = query.source(['title','domain_id','created_at', 'visited_at']).params(request_cache=True)

    if   context["sort"] == "onion":
        query = query.sort("_parent")
    elif context["sort"] == "visited_at":
        query = query.sort("-visited_at")
    elif context["sort"] == "created_at":
        query = query.sort("-created_at")
    elif context["sort"] == "last_seen":
        query = query.sort("-visited_at")

    return query.execute()


def is_elasticsearch_enabled():
    return ('ELASTICSEARCH_ENABLED' in os.environ and os.environ['ELASTICSEARCH_ENABLED'].lower()=='true')



class DomainDocType(Document):
    title = Text(analyzer="snowball")
    created_at = Date()
    visited_at = Date()
    last_alive = Date()
    is_up      = Boolean()
    is_fake    = Boolean()
    is_genuine = Boolean()
    is_crap    = Boolean()
    is_banned  = Boolean()
    url        = Keyword()
    is_subdomain = Boolean()
    ssl        = Boolean()
    port       = Integer()
    domain_id  = Integer()
    domain     = Keyword()
    type       = Keyword()

    class Meta:
        name = 'domain'
        doc_type = 'domain'

    @classmethod
    def get_indexable(cls):
        return cls.get_model().get_objects()

    @classmethod
    def from_obj(klass, obj):
        return klass(
            meta={'id': obj.host},
            title=obj.title,
            created_at=obj.created_at,
            visited_at=obj.visited_at,
            is_up=obj.is_up,
            is_fake=obj.is_fake,
            is_genuine=obj.is_genuine,
            is_crap=obj.is_crap,
            is_banned=obj.is_banned,
            url=obj.index_url(),
            is_subdomain=obj.is_subdomain,
            ssl=obj.ssl,
            port=obj.port,
            domain_id=obj.id,
            domain=obj.host,
            type="domain"
        )

    @classmethod
    def set_isup(klass, obj, is_up):
    	dom = klass(meta={'id': obj.host})
    	dom.update(is_up=is_up)


class PageDocType(Document):
    html_strip = analyzer('html_strip',
        tokenizer="uax_url_email",
        filter=["lowercase", "stop", "snowball", "asciifolding"],
        char_filter=["html_strip"]
    )
    # shingle_filter = token_filter(
    #     'shingle_filter',
    #     type='shingle',
    #     min_shingle_size=2,
    #     max_shingle_size=7
    # )
    # body_analyzer = analyzer(
    #     'body_analyzer',
    #     tokenizer="uax_url_email",
    #     filter=[
    #         "lowercase",
    #         "stop",            
    #         "asciifolding",
    #         shingle_filter
    #     ],
    #     char_filter=["html_strip"]
    # )

    title               = Text(analyzer="snowball")
    title_cleaned       = Text()
    title_raw           = Keyword()
    created_at          = Date()
    visited_at          = Date()
    code                = Integer()
    body                = Text()
    domain_id           = Integer()
    domain              = Keyword()
    body_stripped       = Text(analyzer=html_strip, term_vector="with_positions_offsets")
    body_cleaned        = Text()
    body_stripped_raw   = Keyword()
    is_frontpage        = Boolean()
    published_at        = Date()
    lang_code           = Keyword()
    lang_score          = Float()           
    nid                 = Integer()
    url                 = Keyword()
    type                = Keyword()
    category_label       = Keyword(multi=True)

    class Meta:
        name = 'page'
        doc_type = 'page'

    @classmethod
    def get_indexable(cls):
        return cls.get_model().get_objects()

    @classmethod
    def from_obj(klass, obj, body, is_login=False):
        bodyStripped = tor_text.strip_html(body)
        publishedAt = find_date(body)
        # clean article
        try:
            articleInfo = gooseParser.extract(raw_html=body).infos
            titleCleaned = articleInfo['title']
            bodyCleaned = articleInfo['cleaned_text']
        except Exception as ex:
            traceback.print_exc()
            titleCleaned = ''
            bodyCleaned = ''
        # get language
        try:
            languageInfo = detect_langs(bodyStripped)[0]
            langCode = languageInfo.lang
            langScore = languageInfo.prob
        except:
            langCode = 'unknown'
            langScore = 0.0
        # document type
        documentType = 'surface'
        if is_login:
            documentType = 'marketplace'
        elif obj.domain.host.endswith('.onion'):
            documentType = 'darknet'
        # generate entities
        if langCode in spacyNLP and bodyCleaned.strip() != '':
            doc = spacyNLP[langCode](bodyCleaned.strip())
            for entity in doc.ents:
                entityDoc = EntityDocType.from_obj({
                    'text': entity.text,
                    'label': entity.label_,
                    'url': obj.url,
                    'domain_id': obj.domain.id,
                    'domain': obj.domain.host,
                    'lang_code': langCode,
                    'lang_score': langScore,
                    'updated_at': obj.visited_at,
                })
                entityDoc.save()

        return klass(
            meta={'id':obj.url, 'routing':obj.domain.host},
            title=obj.title,
            title_raw=obj.title,
            title_cleaned=titleCleaned,
            created_at=obj.created_at,
            visited_at=obj.visited_at,
            is_frontpage=obj.is_frontpage,
            published_at=publishedAt,
            lang_code=langCode,
            lang_score=langScore,
            code=obj.code,
            domain_id=obj.domain.id,
            domain=obj.domain.host,
            body=body,
            body_stripped=bodyStripped,
            body_stripped_raw=bodyStripped,
            body_cleaned=bodyCleaned,
            nid=obj.id,
            url=obj.url,
            type=documentType
        )



class EntityDocType(Document):
    text                = Text()   
    label               = Keyword()    
    url                 = Keyword()
    domain_id           = Integer()
    domain              = Keyword()
    lang_code           = Keyword()
    lang_score          = Float()   
    updated_at          = Date() 

    class Meta:
        name = 'entity'
        doc_type = 'entity'

    @classmethod
    def from_obj(klass, data):
        # generate id based on text and label
        uniqueId = hashlib.md5(f"{data['label']}:{data['text']}".encode('utf-8')).hexdigest()
        # return
        return klass(
            meta={'id': uniqueId},
            text=data['text'],
            label=data['label'],
            url=data['url'],
            domain_id=data['domain_id'],
            domain=data['domain'],
            lang_code=data['lang_code'],
            lang_score=data['lang_score'],
            updated_at=data['updated_at'],
        )



class EmailDocType(Document):
    address         = Keyword()
    password        = Keyword()
    text_id         = Keyword()

    class Meta:
        name = 'email'
        doc_type = 'email'

    @classmethod
    def from_obj(klass, address, password="", text_id="scraper"):
        return klass(
            meta={'id': address},
            address=address,
            password=password,
            text_id=text_id
        )


hidden_services = None
email_store = None
entity_store = None

if is_elasticsearch_enabled():
    connections.create_connection(
        hosts=[os.environ['ELASTICSEARCH_HOST']],
        serializer=JSONSerializerPython2(),
        http_auth=(os.environ['ELASTICSEARCH_USERNAME'], os.environ['ELASTICSEARCH_PASSWORD']),
        timeout=int(os.environ['ELASTICSEARCH_TIMEOUT'])
    )
    hidden_services = Index('hiddenservices')
    hidden_services.document(DomainDocType)
    hidden_services.document(PageDocType)

    email_store = Index('emailstore')
    email_store.document(EmailDocType)

    entity_store = Index('entitystore')
    entity_store.document(EntityDocType)


def migrate():
    # hidden service
    hidden_services = Index('hiddenservices')
    hidden_services.delete(ignore=404)
    hidden_services = Index('hiddenservices')
    hidden_services.settings(
        number_of_shards=320,
        number_of_replicas=1,
        # max_shingle_diff=20,
        max_result_window=1000000000,
    )
    hidden_services.document(DomainDocType)
    hidden_services.document(PageDocType)
    hidden_services.create()

    # email store
    email_store = Index('emailstore')
    email_store.delete(ignore=404)
    email_store = Index('emailstore')
    email_store.settings(
        number_of_shards=4,
        number_of_replicas=1,
        max_result_window=1000000000,
    )
    email_store.document(EmailDocType)
    email_store.create()

    # entity store
    entity_store = Index('entitystore')
    entity_store.delete(ignore=404)
    entity_store = Index('entitystore')
    entity_store.settings(
        number_of_shards=4,
        number_of_replicas=1,
        max_result_window=1000000000,
    )
    entity_store.document(EntityDocType)
    entity_store.create()


tracer = logging.getLogger('elasticsearch')
tracer.setLevel(logging.CRITICAL)
url_log = logging.getLogger('urllib3').setLevel(logging.CRITICAL)