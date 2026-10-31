"""Local development server: serves web/ and forwards /api/* to the API, the way nginx does in production (see ops/nginx/).

The frontend calls /api/search, /api/stats and so on. A plain static file server has no /api, so every request from the page would 404.
This stand-in serves the page and strips the /api prefix before forwarding, which is exactly what the production nginx block does.

    python3 ops/dev_server.py                  # page on http://127.0.0.1:8080, API expected on http://127.0.0.1:8000
    python3 ops/dev_server.py --port 9000 --api http://127.0.0.1:8000

Standard library only. For local use: it listens on 127.0.0.1 and has no TLS, no caching and no rate limiting of its own."""
import argparse
import http.server
import os
import urllib.error
import urllib.request

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
FORWARD_HEADERS = ("Content-Type", "Cookie", "Accept", "Accept-Language", "User-Agent")
DROP_RESPONSE_HEADERS = {"transfer-encoding", "connection", "content-length"}


def make_handler(api_base):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=WEB_DIR, **kwargs)

        def _is_api(self):
            return self.path == "/api" or self.path.startswith("/api/") or self.path.startswith("/api?")

        def _proxy(self):
            target = api_base.rstrip("/") + (self.path[len("/api"):] or "/")
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {h: self.headers[h] for h in FORWARD_HEADERS if self.headers.get(h)}
            request = urllib.request.Request(target, data=body, method=self.command, headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=60)
            except urllib.error.HTTPError as error:       # the API answered with a 4xx/5xx: pass it through unchanged
                response = error
            except OSError as error:                       # the API is not running
                payload = ("The API is not reachable at %s (%s). Start it first, see the README." % (api_base, error)).encode()
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            payload = response.read()
            self.send_response(response.status if hasattr(response, "status") else response.code)
            for name, value in response.headers.items():
                if name.lower() not in DROP_RESPONSE_HEADERS:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._proxy() if self._is_api() else super().do_GET()

        def do_HEAD(self):
            self._proxy() if self._is_api() else super().do_HEAD()

        def do_POST(self):
            if self._is_api():
                self._proxy()
            else:
                self.send_error(405)

        def do_DELETE(self):
            if self._is_api():
                self._proxy()
            else:
                self.send_error(405)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="where the API listens (default %(default)s)")
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.api))
    print("Serving web/ on http://127.0.0.1:%d and forwarding /api/* to %s" % (args.port, args.api))
    server.serve_forever()


if __name__ == "__main__":
    main()
