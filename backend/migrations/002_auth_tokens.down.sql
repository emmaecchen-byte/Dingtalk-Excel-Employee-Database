BEGIN;

DROP TABLE IF EXISTS refresh_tokens;

ALTER TABLE users DROP COLUMN IF EXISTS password_hash;
ALTER TABLE users DROP COLUMN IF EXISTS is_active;

DROP INDEX IF EXISTS idx_users_email_unique;

COMMIT;
