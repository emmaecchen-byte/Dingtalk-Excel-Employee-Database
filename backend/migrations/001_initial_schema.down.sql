-- Rollback initial schema (reverse dependency order)

BEGIN;

DROP TABLE IF EXISTS version_history;
DROP TABLE IF EXISTS conflicts;
DROP TABLE IF EXISTS manual_changes;
DROP TABLE IF EXISTS excel_snapshots;
DROP TABLE IF EXISTS monthly_attendance;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS companies;

COMMIT;
