-- Runs once, on first start of an empty data volume.
-- Table DDL lives in backend/db.py (Phase 1); this only sets up extension and schemas.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
