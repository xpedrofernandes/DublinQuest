-- Runs once on a fresh database volume. Quote environment values through psql.
\getenv app_user DATABASE_USER
\getenv app_password DATABASE_PASSWORD
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :DBNAME TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
