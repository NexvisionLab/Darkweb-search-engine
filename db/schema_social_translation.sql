-- Machine translation of non-English social posts (2026-09-20). The original
-- `text` is never modified; the English rendering lives beside it.
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS text_en text;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS translation_engine text;   -- 'qwen' | 'libretranslate'
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS translated_at timestamptz; -- set once the post was looked at, translated or not
CREATE INDEX IF NOT EXISTS social_posts_untranslated_idx ON social_posts (first_seen_at DESC)
    WHERE translated_at IS NULL AND platform = 'telegram';
