-- Migration 002: password authentication + user profiles.
--
-- Applied automatically on startup by backend/app/main.py::_ensure_columns.
-- This file is the explicit, idempotent version for PostgreSQL deployments
-- that manage schema changes out-of-band. It never drops existing data.
--
-- Usage:
--   docker compose exec -T db psql -U postgres -d archschool_db \
--     < backend/migrations/002_user_passwords_profiles.sql

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password VARCHAR(255);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS bio TEXT NOT NULL DEFAULT '';

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;

-- Existing accounts keep working with their 6-character access code.
-- New password registrations are stored as PBKDF2-SHA256 hashes.
UPDATE users
   SET bio = ''
 WHERE bio IS NULL;

COMMIT;
