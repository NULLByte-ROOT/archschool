-- Migration 003: remove the legacy points system, add the toggle anti-abuse
-- table used by the streaks/anti-cheat feature set.
--
-- IMPORTANT (blue-green): run this ONLY after `./deploy.sh deploy` has finished
-- and the previous slot is stopped. The old backend image still selects the
-- `points` / `points_awarded` columns; dropping them while that slot is live
-- would make it fail every user query. The new backend creates the guard table
-- automatically on boot (SQLAlchemy `create_all`), so this script is only
-- needed to physically drop the two dead columns.
--
-- The script is idempotent.
--
-- Usage (PostgreSQL inside the compose stack, after a successful deploy):
--   docker compose exec -T db psql -U postgres -d archschool_db \
--     < backend/migrations/003_stats_streaks_remove_points.sql

BEGIN;

-- 1. Points are gone: ranking is percentage-based now -----------------------
ALTER TABLE users DROP COLUMN IF EXISTS points;
ALTER TABLE assignments DROP COLUMN IF EXISTS points_awarded;

-- 2. Toggle abuse guard (one row per user + assignment) ---------------------
CREATE TABLE IF NOT EXISTS completion_toggle_guards (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assignment_id     INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    window_started_at TIMESTAMP NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    locked_until      TIMESTAMP NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_toggle_guard_user_assignment UNIQUE (user_id, assignment_id)
);

CREATE INDEX IF NOT EXISTS ix_completion_toggle_guards_user_id
    ON completion_toggle_guards (user_id);
CREATE INDEX IF NOT EXISTS ix_completion_toggle_guards_assignment_id
    ON completion_toggle_guards (assignment_id);

COMMIT;
