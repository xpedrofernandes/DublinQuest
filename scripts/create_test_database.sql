-- Run as the database administrator, not as the restricted runtime role.
\getenv app_user DATABASE_USER
\getenv db_name POSTGRES_DB
SELECT 'test_' || :'db_name' AS test_db \gset
SELECT format('CREATE DATABASE %I OWNER %I', :'test_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db') \gexec
\connect :test_db
CREATE EXTENSION IF NOT EXISTS postgis;
