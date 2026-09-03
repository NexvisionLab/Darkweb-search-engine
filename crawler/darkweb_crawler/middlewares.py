class TorProxyMiddleware:
    """Routes every request through the Tor/Privoxy proxy defined in settings.
    A middleware instead of per-spider meta so no future spider can forget it."""

    def __init__(self, proxy):
        self.proxy = proxy

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("TOR_PROXY"))

    def process_request(self, request, spider):
        request.meta["proxy"] = self.proxy
