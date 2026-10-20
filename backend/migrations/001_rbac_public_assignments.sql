-- Migration 001: RBAC roles, public assignments and per-user completion.
--
-- The backend also applies this automatically on startup (see app/main.py,
-- `_ensure_columns` + `_backfill_rbac_data`), so running it by hand is only
-- needed if you manage the schema out-of-band. It is idempotent and never
-- drops existing data.
--
-- Usage (PostgreSQL inside the compose stack):
--   docker compose exec -T db psql -U postgres -d archschool_db \
--     < backend/migrations/001_rbac_public_assignments.sql

BEGIN;

-- 1. User roles -----------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'member';

CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);

-- Legacy admins become role='admin'.
UPDATE users
   SET role = 'admin'
 WHERE is_admin = TRUE
   AND (role IS NULL OR role = 'member');

-- 2. Assignment ownership -------------------------------------------------
ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS creator_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_assignments_creator_id ON assignments (creator_id);

-- Existing rows were owned by their creator.
UPDATE assignments
   SET creator_id = owner_id
 WHERE creator_id IS NULL;

-- 3. Per-user completion table -------------------------------------------
CREATE TABLE IF NOT EXISTS assignment_completions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    completed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_completion_user_assignment UNIQUE (user_id, assignment_id)
);

CREATE INDEX IF NOT EXISTS ix_assignment_completions_user_id
    ON assignment_completions (user_id);
CREATE INDEX IF NOT EXISTS ix_assignment_completions_assignment_id
    ON assignment_completions (assignment_id);

-- Preserve the completion state of already-finished assignments.
INSERT INTO assignment_completions (user_id, assignment_id, completed_at)
SELECT a.owner_id, a.id, COALESCE(a.updated_at, CURRENT_TIMESTAMP)
  FROM assignments a
 WHERE a.completed = TRUE
   AND a.owner_id IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM assignment_completions c
        WHERE c.assignment_id = a.id AND c.user_id = a.owner_id
   );

COMMIT;
