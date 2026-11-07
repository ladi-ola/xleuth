-- Public landing-page signups. The API ensures this idempotent schema at boot;
-- operators can also apply it explicitly. Do not run the down migration on hosted data.
CREATE TABLE IF NOT EXISTS waitlist_entries (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'landing',
    sync_status TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending', 'synced', 'failed')),
    synced_at TIMESTAMPTZ,
    sync_error VARCHAR(200)
);

-- Upgrade installations with the earlier consent-required waitlist, preserving
-- historical consent_at values. The API also applies this automatically.
ALTER TABLE waitlist_entries ADD COLUMN IF NOT EXISTS sync_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE waitlist_entries ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ;
ALTER TABLE waitlist_entries ADD COLUMN IF NOT EXISTS sync_error VARCHAR(200);
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'waitlist_entries'::regclass
          AND conname = 'waitlist_entries_sync_status_check'
    ) THEN
        ALTER TABLE waitlist_entries ADD CONSTRAINT waitlist_entries_sync_status_check
            CHECK (sync_status IN ('pending', 'synced', 'failed'));
    END IF;
END $$;
-- On an older table only (skip on fresh installations):
-- ALTER TABLE waitlist_entries ALTER COLUMN consent_at DROP NOT NULL;
-- ALTER TABLE waitlist_entries ALTER COLUMN consent_at DROP DEFAULT;
