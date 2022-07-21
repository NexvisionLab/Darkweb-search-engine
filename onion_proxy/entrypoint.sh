#!/bin/bash

sleep 30

# Retart HAProxy
echo "Restarting haproxy"
service haproxy restart

# just keep
tail -f /dev/null