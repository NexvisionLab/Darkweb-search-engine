FROM dockage/alpine:3.9-openrc

RUN apk --no-cache --update add tor privoxy \
    && mv /etc/tor/torrc.sample /etc/tor/torrc \
    && echo "forward-socks5 / 0.0.0.0:9050 ." >> /etc/privoxy/config \
    && sed -i 's/listen-address\s*127.0.0.1:8118/listen-address 0.0.0.0:8100/g' /etc/privoxy/config \
    && sed -i 's/#SOCKSPort 192.168.0.1:9100/SOCKSPort 0.0.0.0:9050/g' /etc/tor/torrc \
    && rc-update add tor \
    && rc-update add privoxy

EXPOSE 9050/tcp 8100/tcp
