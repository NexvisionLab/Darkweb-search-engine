# MSS clamp (tun0)

Fixes the PMTUD blackhole on the Astrill VPN tunnel (MTU 1293) by clamping
TCP MSS on outbound tun0 traffic, instead of routing around the VPN.

## Why this exists

`ops/web-bypass` (removed) tried to fix the same MTU problem by routing the
web server's port 80/443 reply traffic via the native gateway (`ens33`)
instead of `tun0`. That broke public reachability entirely: replies sent via
`ens33` get NATed to a different public IP (`<other-public-ip>`) than the one
DNS publishes for darknyx.com and the one the client's connection actually
came in on (`<vpn-tunnel-public-ip>`, via `tun0`). Any externally-initiated
connection became unroutable - this took the site down.

MSS clamping fixes the same underlying MTU problem without changing which
interface or path traffic takes, so it has none of that failure mode. This
is the same pattern already used for outbound Docker/AWS CloudFront pulls
in `ops/aws-bypass/`, applied here as a general per-tunnel clamp instead of
a per-destination route.

## Install (requires root)

```
sudo cp ops/mss-clamp/darkweb-mss-clamp.sh /usr/local/sbin/
sudo chmod +x /usr/local/sbin/darkweb-mss-clamp.sh
sudo cp ops/mss-clamp/darkweb-mss-clamp.service ops/mss-clamp/darkweb-mss-clamp.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now darkweb-mss-clamp.timer
sudo systemctl start darkweb-mss-clamp.service
```

Verify:
```
sudo iptables -t mangle -L POSTROUTING -v -n | grep TCPMSS
systemctl status darkweb-mss-clamp.timer
```

## Removing the old broken bypass from the live server (if not already done)

```
sudo systemctl disable --now darkweb-web-bypass.timer
sudo rm -f /etc/systemd/system/darkweb-web-bypass.service /etc/systemd/system/darkweb-web-bypass.timer /usr/local/sbin/darkweb-web-bypass.sh
sudo systemctl daemon-reload
sudo ip rule del sport 80 table 200 2>/dev/null || true
sudo ip rule del sport 443 table 200 2>/dev/null || true
```
