# TODO

## Security / cleanup

- [ ] Change `eklabs_migrator` and `eklabs_app` passwords to something stronger
      than what was used during initial setup:
      ```sql
      ALTER ROLE eklabs_migrator PASSWORD '...';
      ALTER ROLE eklabs_app PASSWORD '...';
      ```

## Not done yet

- [ ] Set up and test `APP_DATABASE_URL` (the transaction-pooler connection
      the running app/tests use — `eklabs_app` role, port 6543). Only the
      migrator/direct-connection side has been exercised so far.
- [ ] Install the Supabase CLI (`winget install Supabase.CLI` or
      `npx supabase@latest`) and run `supabase init` + `supabase start` to get
      a local Postgres instance — needed to actually run the `pytest` suite in
      `src/eklabs_platform/core/tests/` that proves tenant isolation works.
- [ ] Once the test suite runs locally, wire it into GitHub Actions CI
      (build-guide step 6 — not done yet).
- [ ] Reconcile CLAUDE.md's "Full stack (local): `docker compose up`" command
      now that Postgres comes from `supabase start` instead — `docker-compose.yml`
      still covers Redis/Neo4j/anything else that isn't part of Supabase.
- [ ] `role_binding` / authorization — `app_user` currently has no `role`
      column; nothing is actually authorized against these tables yet.
- [ ] The FastAPI `apps/api` dependency that resolves a request's tenant from
      auth context (Clerk) and calls `tenant_scoped_session()` — doesn't exist
      yet, `apps/api` hasn't been built.

## Facts worth remembering (bit us once already)

- Supabase's actual Postgres version is **17.6**, not "16" as CLAUDE.md's
  stack line currently says.
- A role needs `GRANT CREATE ON DATABASE postgres` to run `CREATE SCHEMA`,
  even with `IF NOT EXISTS` — schema creation is a database-level privilege,
  not a schema-level one.
- Resolving an unqualified type like `vector` requires **both** `GRANT USAGE
  ON SCHEMA extensions` **and** `extensions` being in the role's
  `search_path` (`ALTER ROLE ... SET search_path TO public, extensions`) —
  granting only one of the two isn't enough.
- Supabase's **direct** connection host (`db.<ref>.supabase.co`) is
  IPv6-only by default; use the **session pooler**
  (`aws-0-<region>.pooler.supabase.com:5432`, username
  `<role>.<project-ref>`) for anything run from a network without IPv6.
