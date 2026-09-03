#!/bin/bash
# Clamps TCP MSS on tun0 (Astrill VPN, MTU 1293) to the tunnel's real path
# MTU. This is the correct fix for the PMTUD-blackhole class of problem on
# this VM - the same class that first broke Docker/AWS CloudFront pulls
# (see ops/aws-bypass/) and later took darknyx.com itself offline when
# ops/web-bypass tried to solve it by routing web replies around the VPN
# instead. That approach broke inbound reply-IP consistency: replies sent
# out via the native gateway (ens33) get NATed to a different public IP
# than the one DNS points at and the client connected to, so every
# externally-initiated request became unroutable. MSS clamping fixes the
# MTU problem without changing which interface or path traffic uses, so it
# doesn't have that failure mode - safe for a server whose whole job is
# receiving inbound connections.
set -e

iptables -t mangle -C POSTROUTING -o tun0 -p tcp --tcp-flags SYN,RST SYN \
  -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || \
iptables -t mangle -A POSTROUTING -o tun0 -p tcp --tcp-flags SYN,RST SYN \
  -j TCPMSS --clamp-mss-to-pmtu

logger -t darkweb-mss-clamp "applied: TCP MSS clamped to PMTU on tun0"
