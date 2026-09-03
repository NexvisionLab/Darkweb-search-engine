CREATE TABLE IF NOT EXISTS domains (
    id             BIGSERIAL PRIMARY KEY,
    host           TEXT NOT NULL UNIQUE,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_up          BOOLEAN NOT NULL DEFAULT true,
    title          TEXT,
    safety_rating  TEXT NOT NULL DEFAULT 'unrated'
);

CREATE TABLE IF NOT EXISTS pages (
    id           BIGSERIAL PRIMARY KEY,
    domain_id    BIGINT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    url          TEXT NOT NULL UNIQUE,
    title        TEXT,
    body_text    TEXT,
    http_status  INT,
    crawled_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain_id);

ALTER TABLE pages ADD COLUMN IF NOT EXISTS content_category TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS pii_present BOOLEAN;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS ransomware_victims (
    id            BIGSERIAL PRIMARY KEY,
    group_name    TEXT NOT NULL,
    victim_name   TEXT NOT NULL,
    discovered_at TIMESTAMPTZ,
    source        TEXT NOT NULL DEFAULT 'ransomlook',
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (group_name, victim_name, discovered_at)
);
CREATE INDEX IF NOT EXISTS idx_ransomware_victims_group ON ransomware_victims(group_name);
CREATE INDEX IF NOT EXISTS idx_ransomware_victims_discovered ON ransomware_victims(discovered_at DESC);

CREATE TABLE IF NOT EXISTS page_prices (
    id           BIGSERIAL PRIMARY KEY,
    page_id      BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    domain_id    BIGINT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    amount       NUMERIC NOT NULL,
    currency     TEXT NOT NULL,
    raw_text     TEXT,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_page_prices_domain ON page_prices(domain_id);
CREATE INDEX IF NOT EXISTS idx_page_prices_page ON page_prices(page_id);
CREATE TABLE IF NOT EXISTS breach_emails (
    email_hash     TEXT PRIMARY KEY,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sighting_count INT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS watchlists (
    id             BIGSERIAL PRIMARY KEY,
    keyword        TEXT NOT NULL,
    webhook_url    TEXT NOT NULL,
    unsubscribe_token TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_triggered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_watchlists_keyword ON watchlists (lower(keyword));

CREATE TABLE IF NOT EXISTS site_reports (
    id           BIGSERIAL PRIMARY KEY,
    host         TEXT NOT NULL,
    reason       TEXT NOT NULL,
    reported_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status       TEXT NOT NULL DEFAULT 'pending',
    resolved_at  TIMESTAMPTZ,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_site_reports_status ON site_reports (status);

CREATE TABLE IF NOT EXISTS verification_claims (
    id           BIGSERIAL PRIMARY KEY,
    host         TEXT NOT NULL,
    token        TEXT NOT NULL UNIQUE,
    contact      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_verification_claims_host ON verification_claims (host);

ALTER TABLE domains ADD COLUMN IF NOT EXISTS owner_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS clone_suspect BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS malware_link_flag BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS exit_scam_suspect BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS preview_updated_at TIMESTAMPTZ;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS favicon_url TEXT;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS favicon_captured_at TIMESTAMPTZ;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS meta_description TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE ransomware_victims ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE ransomware_victims ADD COLUMN IF NOT EXISTS link TEXT;
ALTER TABLE ransomware_victims ADD COLUMN IF NOT EXISTS magnet TEXT;
ALTER TABLE ransomware_victims ADD COLUMN IF NOT EXISTS has_screenshot BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ransomware_victims ADD COLUMN IF NOT EXISTS detail_fetched_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS discovery_candidates (
    id               BIGSERIAL PRIMARY KEY,
    host             TEXT NOT NULL UNIQUE,
    discovered_from  TEXT,
    discovered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT NOT NULL DEFAULT 'pending',
    verified_at      TIMESTAMPTZ,
    title            TEXT
);
CREATE INDEX IF NOT EXISTS idx_discovery_candidates_status ON discovery_candidates (status);

CREATE TABLE IF NOT EXISTS page_entities (
    id           BIGSERIAL PRIMARY KEY,
    page_id      BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    domain_id    BIGINT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    entity_type  TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(page_id, entity_type, entity_value)
);
CREATE INDEX IF NOT EXISTS idx_page_entities_lookup ON page_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_page_entities_page ON page_entities(page_id);

-- extracted_at now means "first seen" (set once, never updated again -
-- rows that predate this migration already lost their true first-seen
-- time to the old clear-and-reinsert behavior, so their extracted_at is
-- only an approximation). last_seen_at/sighting_count refresh on every
-- re-crawl that reconfirms the same value; still_present flips false
-- (row is kept, not deleted) when a re-crawl no longer finds it.
ALTER TABLE page_entities ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE page_entities ADD COLUMN IF NOT EXISTS sighting_count INT NOT NULL DEFAULT 1;
ALTER TABLE page_entities ADD COLUMN IF NOT EXISTS still_present BOOLEAN NOT NULL DEFAULT true;
CREATE INDEX IF NOT EXISTS idx_page_entities_value_last_seen ON page_entities(entity_type, entity_value, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS digest_subscriptions (
    id                BIGSERIAL PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE,
    subscribed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    unsubscribe_token TEXT NOT NULL UNIQUE,
    active            BOOLEAN NOT NULL DEFAULT true
);

ALTER TABLE pages ADD COLUMN IF NOT EXISTS image_urls TEXT[];
ALTER TABLE pages ADD COLUMN IF NOT EXISTS image_ocr_text TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS image_qr_text TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS images_processed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS authenticated_sessions (
    id                 BIGSERIAL PRIMARY KEY,
    host               TEXT NOT NULL UNIQUE,
    cookies_encrypted  BYTEA NOT NULL,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ,
    last_used_at       TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ
);

ALTER TABLE domains ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'tor';
