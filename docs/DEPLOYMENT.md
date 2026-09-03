# Deployment guide

This walks through a real production deployment on a single Linux VM (this
is exactly how the reference deployment runs, with the server's real
identity replaced by placeholders). Adjust paths/users to taste — nothing
here requires this exact layout.

Conventions used below: dedicated user `darknyx`, install root `/opt/darknyx`.

## 1. Prerequisites

- A Linux VM with Docker, Python 3.11+, and outbound internet access.
- A **Tor egress path**. If your VM's own network already reaches Tor fine,
  the bundled `tor-proxy/` container is all you need. If your provider's
  network has routing quirks (see the PMTUD note in `ops/mss-clamp/`), you
  may need additional fixes specific to your environment.
- A domain name, if you want HTTPS (recommended) — this guide uses
  certbot + DNS-01 via GoDaddy's API as one concrete example; swap in
  whatever DNS provider and ACME client you actually use.

## 2. Clone and configure

```bash
sudo useradd -m -d /opt/darknyx darknyx
sudo -u darknyx git clone <this-repo> /opt/darknyx
cd /opt/darknyx
sudo -u darknyx cp .env.example .env
sudo -u darknyx nano .env   # fill in every value - see the comments in the file
```

Generate the two secrets `.env.example` can't provide a real default for:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # ADMIN_TOKEN
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # SESSION_ENCRYPTION_KEY
```

## 3. Backing services

```bash
cd /opt/darknyx
sudo -u darknyx docker compose up -d postgres opensearch redis tor-privoxy-0
sudo -u darknyx docker exec -i darkweb-postgres psql -U darknyx -d darknyx < db/schema.sql
```

`db/schema.sql` is idempotent — safe to re-run after every pull that touches
the schema.

## 4. Python environments

Each of `api/`, `crawler/` needs its own virtualenv (they're deliberately
independent, deployable/scalable separately):

```bash
cd /opt/darknyx/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd /opt/darknyx/crawler && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## 5. The local AI summarizer (optional but recommended)

Community on-demand page summarization runs a local llama.cpp server. Download
a GGUF build of Qwen3.5-4B (or any instruction-tuned model llama.cpp
supports — adjust `--chat_format` in the systemd unit accordingly) into
`/opt/darknyx/ai/models/`, then:

```bash
python3 -m venv /opt/darknyx/ai/.venv
/opt/darknyx/ai/.venv/bin/pip install llama-cpp-python fastapi uvicorn
```

## 6. systemd units

Everything in `ops/` is a template — copy, adjust the `User=`/paths if you
didn't use the `darknyx` user + `/opt/darknyx` convention, then install:

```bash
sudo cp ops/systemd/*.service ops/systemd/*.timer /etc/systemd/system/
sudo cp ops/scheduled-crawl/darkweb-pipeline.sh /usr/local/sbin/
sudo chmod +x /usr/local/sbin/darkweb-pipeline.sh
sudo cp ops/scheduled-crawl/darkweb-pipeline.service ops/scheduled-crawl/darkweb-pipeline.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now darkweb-summarizer.service   # local AI, if installed in step 5
sudo systemctl start darkweb-summarizer.service

# then the API itself
sudo tee /etc/systemd/system/darkweb-api.service > /dev/null <<'EOF'
[Unit]
Description=DarkNyx public API
After=network.target
[Service]
Type=simple
User=darknyx
WorkingDirectory=/opt/darknyx
EnvironmentFile=/opt/darknyx/.env
ExecStart=/opt/darknyx/api/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now darkweb-api.service

# recurring crawl + enrichment
sudo systemctl enable --now darkweb-pipeline.timer
# preview screenshots, image OCR, ransomware mirror previews, digest email
sudo systemctl enable --now darkweb-preview-capture.timer darkweb-image-ocr.timer darkweb-digest.timer
```

Verify each with `systemctl status <unit>` and, for timers,
`systemctl list-timers 'darkweb-*'` — confirm a timer actually shows a real
next/last-run time, not just `enabled`.

**A real lesson learned building this**: killing a systemd-managed process
with a bare `kill` does *not* trigger `Restart=on-failure` — systemd treats
that as an intentional stop. After any `enable --now`, verify with
`ss -ltnp` (not just `systemctl is-active`) that the *new* systemd-owned
process actually holds the port; a stale manually-started process can
silently keep holding it and mask a failed unit.

## 7. nginx + TLS

`ops/nginx/darknyx.com.conf` is a real, hardened nginx config (CSP, HSTS,
X-Frame-Options, X-Content-Type-Options) — copy it, replace `darknyx.com`
with your own domain, and point the `/api/` location block at the port your
`darkweb-api.service` is listening on.

For TLS via DNS-01 (needed if you're behind a VPN/NAT that blocks HTTP-01,
or just prefer it): `ops/https-godaddy/darknyx-dns-auth.sh` is a working
certbot `--manual-auth-hook` for GoDaddy's DNS API — set `GODADDY_API_KEY`
in `.env` and adapt the script if you use a different registrar (the pattern
— PUT a TXT record via your registrar's API, sleep for propagation — is the
same everywhere; only the API call changes).

```bash
sudo certbot certonly --manual --preferred-challenges dns \
  --manual-auth-hook /opt/darknyx/ops/https-godaddy/darknyx-dns-auth.sh \
  -d yourdomain.com
```

## 8. Network quirks (read if your VPN/provider does something unusual)

`ops/mss-clamp/` and `ops/aws-bypass/` document two real PMTUD (path-MTU
discovery) issues found running this behind a VPN tunnel with a small MTU:
large transfers silently stalling, and AWS/CloudFront ranges specifically
black-holing. Neither applies if your network path is ordinary — read the
READMEs in each directory before installing either; they explain the actual
symptom to look for.

## 9. First crawl

```bash
cd /opt/darknyx/crawler
source ../.env && source .venv/bin/activate
python3 scripts/import_ransomlook_seeds.py --limit 60 --out seeds_runtime.txt
scrapy crawl onion -a seeds_file=seeds_runtime.txt -s DEPTH_LIMIT=1
python3 scripts/reindex_opensearch.py
```

For a much larger first crawl, use `onions_list/onions.txt` (~19,000
unverified addresses — see [onions_list/README.md](../onions_list/README.md))
instead of or alongside the RansomLook-sourced seeds:

```bash
scrapy crawl onion -a seeds_file=../onions_list/onions.txt -s DEPTH_LIMIT=1
```

After this, `darkweb-pipeline.timer` keeps the corpus fresh automatically —
see `ops/scheduled-crawl/darkweb-pipeline.sh` for the exact step sequence it
runs (seed refresh, crawl, price/entity/breach-email backfills, liveness
checks, exit-scam detection, preview/favicon capture, reindex).

## Security checklist before going live

- [ ] SSH: key-only auth, `fail2ban` or equivalent for brute-force protection.
- [ ] `.env` is `chmod 600`, owned by the service user, never committed.
- [ ] Postgres/OpenSearch/Valkey bound to `127.0.0.1` only (already the
      default in `docker-compose.yml`) — never expose these ports publicly.
- [ ] `ADMIN_TOKEN` is a real random value, not the placeholder.
- [ ] Firewall allows only 80/443 (and SSH) from the public internet.
