-- Social & narrative intelligence, ingest layer (2026-09-19; scope in
-- the plans dir, social-narrative-intelligence-scope.md). Sources are
-- free/open only: Bluesky Jetstream, Mastodon public timelines, public
-- Telegram channel preview pages. Posts are FILTERED AT INGEST (a post
-- is stored only if it matches a threat-relevant signal - see
-- social_ingest.py), not archived wholesale, and expire after 30 days
-- (data minimisation). Idempotent, safe to re-run.
CREATE TABLE IF NOT EXISTS social_posts (
    id            BIGSERIAL PRIMARY KEY,
    platform      TEXT NOT NULL,            -- bluesky | mastodon | telegram
    source        TEXT NOT NULL,            -- instance host, channel handle, or 'jetstream'
    external_id   TEXT NOT NULL,            -- platform-native post id
    author_id     TEXT,                     -- did / acct / channel - stable identifier
    author_handle TEXT,                     -- display handle where the source gives one
    text          TEXT NOT NULL,
    lang          TEXT,
    url           TEXT,
    posted_at     TIMESTAMPTZ,
    hashtags      TEXT[] NOT NULL DEFAULT '{}',
    links         TEXT[] NOT NULL DEFAULT '{}',
    media_urls    TEXT[] NOT NULL DEFAULT '{}',   -- recorded, never fetched by the ingest layer
    keep_reasons  TEXT[] NOT NULL DEFAULT '{}',   -- why this post passed the ingest filter
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 days',
    UNIQUE (platform, external_id)
);
CREATE INDEX IF NOT EXISTS idx_social_posts_posted ON social_posts(posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_author ON social_posts(platform, author_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_expires ON social_posts(expires_at);
CREATE INDEX IF NOT EXISTS idx_social_posts_fts ON social_posts USING gin (to_tsvector('simple', text));

CREATE TABLE IF NOT EXISTS social_post_entities (
    post_id      BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    entity_type  TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    PRIMARY KEY (post_id, entity_type, entity_value)
);
CREATE INDEX IF NOT EXISTS idx_social_post_entities_lookup ON social_post_entities(entity_type, lower(entity_value));

-- Resume points: Jetstream time_us, Mastodon since_id per timeline,
-- Telegram highest message id per channel.
CREATE TABLE IF NOT EXISTS social_cursors (
    platform   TEXT NOT NULL,
    source     TEXT NOT NULL,
    cursor     TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, source)
);

-- Public Telegram channels to poll. Seeded from telegram handles the
-- dark-web crawl already found; operators can add more. A handle that
-- turns out not to be a public channel (a user/bot page) is marked
-- inactive rather than retried forever.
CREATE TABLE IF NOT EXISTS social_telegram_channels (
    handle         TEXT PRIMARY KEY,
    origin         TEXT NOT NULL DEFAULT 'crawl',   -- crawl | operator
    active         BOOLEAN NOT NULL DEFAULT true,
    added_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_polled_at TIMESTAMPTZ,
    last_error     TEXT
);

-- Whether the darknyx.com Free site may show this channel's recent posts. Off until an
-- operator publishes it (social_maintenance.py publish-channel): channels can carry
-- leaked personal data and unreviewed content, so exposure is opt-in per channel.
ALTER TABLE social_telegram_channels ADD COLUMN IF NOT EXISTS public BOOLEAN NOT NULL DEFAULT false;

-- Channels found by scripts/social_telegram_discover.py, waiting for a human decision. A
-- candidate is only a pointer (a t.me link in a stored post, a RansomLook record, a search
-- hit) plus one probe of its public preview; approving one adds it to the poll list above.
CREATE TABLE IF NOT EXISTS social_telegram_candidates (
    handle         TEXT PRIMARY KEY,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sources        TEXT[] NOT NULL DEFAULT '{}',   -- posts | ransomlook | search
    referrers      TEXT[] NOT NULL DEFAULT '{}',   -- up to 5 places that pointed at it
    mentions       INTEGER NOT NULL DEFAULT 1,
    probe_status   TEXT,                           -- readable | no_preview | error
    probed_at      TIMESTAMPTZ,
    preview_posts  INTEGER,
    relevance_hits INTEGER,                        -- newest posts that pass the ingest filter on their own
    sample         TEXT,
    status         TEXT NOT NULL DEFAULT 'new',    -- new | approved | rejected
    decided_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tg_candidates_status ON social_telegram_candidates(status, probe_status);

-- Erasure requests (GDPR): posts by these authors are deleted and never
-- re-ingested.
CREATE TABLE IF NOT EXISTS social_suppressed_authors (
    platform   TEXT NOT NULL,
    author_key TEXT NOT NULL,                       -- lower-cased author_id or handle
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, author_key)
);
