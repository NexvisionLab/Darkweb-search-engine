FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tor privoxy ca-certificates && rm -rf /var/lib/apt/lists/*
COPY torrc /etc/tor/torrc
COPY privoxy-config /etc/privoxy/config
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8118 9050
ENTRYPOINT ["/entrypoint.sh"]
