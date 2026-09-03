BOT_NAME = "darkweb_crawler"

SPIDER_MODULES = ["darkweb_crawler.spiders"]
NEWSPIDER_MODULE = "darkweb_crawler.spiders"

ROBOTSTXT_OBEY = False  # onion services have no meaningful robots.txt convention

# Onion services are slow and often unreliable - be patient, not aggressive.
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 2
DOWNLOAD_TIMEOUT = 60
RETRY_TIMES = 2
DEPTH_LIMIT = 3

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

ITEM_PIPELINES = {
    "darkweb_crawler.pipelines.DiscoveryPipeline": 250,
    "darkweb_crawler.pipelines.PostgresPipeline": 300,
    "darkweb_crawler.pipelines.EnrichmentPipeline": 350,
    "darkweb_crawler.pipelines.DBUpdatePipeline": 360,
    "darkweb_crawler.pipelines.OpenSearchPipeline": 400,
}

# Every request is routed through Privoxy -> Tor. Set once here rather than
# per-spider so it can never be accidentally forgotten on a new spider.
import os
TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")

DOWNLOADER_MIDDLEWARES = {
    "darkweb_crawler.middlewares.TorProxyMiddleware": 350,
}

LOG_LEVEL = "INFO"
