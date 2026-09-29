-- One-time role bootstrap, run once per Supabase project (local `supabase
-- start` instance, staging, production) BEFORE the first `alembic upgrade
-- head` — the migrator role must exist before Alembic can even connect.
--
-- Not an Alembic migration (nothing here is app schema) and not a
-- docker-entrypoint-initdb.d script (Supabase doesn't offer that hook for
-- hosted projects) — just a plain SQL file run once via psql:
--
--   psql "$SUPABASE_DB_URL" \
--     -v migrator_password="$ECLABS_MIGRATOR_PASSWORD" \
--     -v app_password="$EKLABS_APP_PASSWORD" \
--     -f src/platform/core/db/bootstrap/01_roles.sql
--
-- Passwords are passed in as psql variables, never hardcoded here.
--
-- eklabs_migrator: owns every table (whichever role runs CREATE TABLE
-- becomes owner automatically), used only by `alembic upgrade head`.
-- eklabs_app: unprivileged runtime role used by the app and by the tenant
-- isolation tests. Deliberately NOT the owner, NOT superuser, and NEVER
-- granted BYPASSRLS — Postgres RLS never applies to superusers and never
-- applies to a table's owner unless FORCE ROW LEVEL SECURITY is set, so
-- connecting as either would make the isolation tests pass by bypassing RLS
-- entirely rather than by RLS actually blocking them.
--
-- Supabase's own predefined roles (postgres, anon, authenticated,
-- service_role, ...) exist for its Auth/PostgREST layer and are unrelated —
-- this app connects directly via SQLAlchemy, never through PostgREST.

CREATE ROLE eklabs_migrator LOGIN PASSWORD :'migrator_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE ROLE eklabs_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- Supabase's default database is named "postgres" for every project.
GRANT CONNECT ON DATABASE postgres TO eklabs_migrator, eklabs_app;

GRANT USAGE, CREATE ON SCHEMA public TO eklabs_migrator;
GRANT USAGE ON SCHEMA public TO eklabs_app;

-- vector lives in the extensions schema (migration 0001); eklabs_app only
-- needs to resolve the `vector` type through the search_path, not own it.
GRANT USAGE ON SCHEMA extensions TO eklabs_app;
