#!/bin/sh
set -e
tor -f /etc/tor/torrc &
TOR_PID=$!
sleep 8
exec privoxy --no-daemon /etc/privoxy/config
