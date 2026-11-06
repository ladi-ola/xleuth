-- Public landing-page signups. The API ensures this idempotent schema at boot;
-- operators can also apply it explicitly. Do not run the down migration on hosted data.
CREATE TABLE IF NOT EXISTS waitlist_entries (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'landing'
);
