#!/bin/sh
http_proxy="" https_proxy="" wget --no-check-certificate --tries=1 -T 10  -O - $1 | grep -E -o '[\w\-\.]+\.onion'
