# Access Control: Tags

This package implements tag-based access control for the Tiled catalog. Access to
nodes (arrays, containers) is governed by **tags** that are compiled into a SQLite
database and loaded by Tiled at startup.

---

## Definitions

### Role

A named set of Tiled scopes. Two roles are defined in
[`tag_definitions_stub.yaml`](src/splash_tiled/access_control/tag_definitions_stub.yaml):

| Role | Scopes |
|---|---|
| `facility_user` | `read:data`, `read:metadata` |
| `facility_admin` | read + write + delete + create + register |

### Tag

A named group of principals (users or ORCID groups) and the role they hold within
that tag. A node in the catalog is tagged by attaching one or more tag names to it;
only principals that are members of those tags can access the node.

```yaml
# Example: everyone in the SB-01482-001 ESAF group gets read access
SB-01482-001:
  groups:
    - name: SB-01482-001   # resolved to a list of ORCIDs at compile time
      role: facility_user
```

### Auto-tag

A list of additional tags that are automatically applied whenever a node is tagged
with a given tag. If a node is tagged with `SB-01482-001`, Tiled also applies every
tag listed under its `auto_tags`, without the data writer having to name them
explicitly.

```yaml
SB-01482-001:
  auto_tags:
    - name: data_admin       # data admins automatically see every ESAF node
    - name: 12.3.2-staff     # beamline staff automatically see their own ESAFs
```

### Tag owner

A set of principals that are allowed to *apply* a tag to a node. Defined in
`tag_owners`. If omitted for a tag, only Tiled admins can apply it.

### Compiled tags database

`compiled_tags.db` — the output of the `tiled_tags compile` command. It
resolves every group name to a concrete list of user identities (ORCIDs) and stores
the results in a form that Tiled can query at request time. Tiled reloads this file
automatically; no server restart is required after a recompile.

---

## How tags are used for proposals, staff, and auto-tags

### ESAF / proposal tags

Each ESAF (Experiment Safety Approval Form) is identified by a **friendly ID** such
as `SB-01482-001`. During compilation, one tag is emitted per ESAF:

```yaml
SB-01482-001:
  groups:
    - name: SB-01482-001    # ESAF participants (resolved from User Office)
      role: facility_user
    - name: 12.3.2-staff    # beamline staff also get read access
      role: facility_user
  auto_tags:
    - name: data_admin      # site-wide data admins always inherit access
    - name: 12.3.2-staff    # beamline staff tag applied automatically
```

A data writer tags a node with `SB-01482-001`. Tiled then grants read access to:
- every participant listed in that ESAF (resolved via their ORCID)
- every staff member of beamline `12.3.2`
- everyone in the `data_admin` tag

### Beamline staff tags

Each beamline gets an explicit staff tag of the form `<beamline>-staff` (e.g.
`12.3.2-staff`). The group is populated from the User Office "beamline staff"
endpoint and compiled to a list of ORCIDs.

```yaml
12.3.2-staff:
  groups:
    - name: 12.3.2-staff
      role: facility_user
```

Staff tags can be applied directly to a node to grant access without requiring an
ESAF — for example, internal beamline commissioning data. They are also applied
automatically via `auto_tags` on every ESAF tag for that beamline (see above).

### Static / administrative tags

Tags such as `data_admin` are defined statically in
[`tag_definitions_stub.yaml`](src/splash_tiled/access_control/tag_definitions_stub.yaml) and list named users rather than
dynamically resolved groups:

```yaml
data_admin:
  users:
    - name: cara
      role: facility_admin
```

These are merged verbatim into the generated YAML and compiled alongside the
dynamic ESAF/staff tags.

### Tag flow summary

```
node tagged with SB-01482-001
        │
        ├─ SB-01482-001 group  →  ESAF participants  (facility_user)
        ├─ 12.3.2-staff group  →  beamline staff     (facility_user)
        │
        └─ auto_tags applied automatically:
               data_admin      →  site admins        (facility_admin)
               12.3.2-staff    →  beamline staff     (facility_user)
```

---

## The `access` CLI

All compile and query operations are available through the `access` command.

```
access compile all            # sync User Office APIs then compile tags
access compile useroffice     # sync User Office APIs only (writes esafs.db)
access compile compiled-tags  # compile tags from existing esafs.db

access query beamlines
access query proposals [--beamline 12.3.2] [--proposal SB]
access query esaf    [--beamline 12.3.2] [--proposal SB]
access query proposal-members <esaf-friendly-id>
access query beamline-members <beamline>
access query user-proposals   <orcid>
access query user-beamlines   <orcid>
access query tags             <orcid>
```

All compile subcommands default to `tags/esafs.db` and `tags/compiled_tags.db`.
All query subcommands default to `--db-path tags/esafs.db` and
`--compiled-db tags/compiled_tags.db`.

### Running from a container

The `access-ctl` service is defined in `docker-compose.yaml` with
`profiles: [access]` so it never starts automatically. Use
`docker compose run` to invoke it on demand:

```bash
docker compose run --rm access-ctl compile all
docker compose run --rm access-ctl query beamline-members 12.3.2
docker compose run --rm access-ctl query tags 0000-0002-3979-8844
```

---

## How to run an update

Updates are normally performed automatically by the `sync-worker` container on the
schedule configured by `SYNC_CRON`. To trigger a manual update from the host:

```bash
# Full update: sync User Office APIs then compile tags
access compile all

# Or as two separate steps:
access compile useroffice
access compile compiled-tags
```

Tiled picks up the new `compiled_tags.db` automatically — no restart needed.

### Environment variables (sync-worker)

| Variable | Default | Description |
|---|---|---|
| `SYNC_CRON` | — | Cron expression for automatic sync (required) |
| `BEAMLINES` | `12.3.2,9.3.2,7.0.2` | Comma-separated beamline list, or `all` |
| `ESAF_DB_PATH` | `/app/tags/esafs.db` | Path to the ESAF SQLite database |
| `TAGS_TEMPLATE` | `/app/src/.../tag_definitions_stub.yaml` | Static tag definitions template |
| `GENERATED_TAGS_YAML` | `/app/tags/tag_definitions.generated.yml` | Generated YAML output path |
| `COMPILED_TAGS_DB` | `/app/tags/compiled_tags.db` | Compiled tags output path |

---

## How to run the integration test

An integration test is provided to verify that the tag compilation process works end-to-end with live data from the User Office API. This test is **skipped by default** to avoid hitting external services during normal test runs.

To run the integration test:

1. Ensure you have network access to the User Office API and any required credentials or environment variables set (see project README for details).
2. Run pytest with the `--user-office` marker enabled:

  ```bash
  pixi run pytest -m user_office
  ```

  Or, if running directly:

  ```bash
  pytest -m user_office
  ```

3. The test is located in `tests/test_user_office_integration.py`. It will call the User Office API, trigger tag compilation, and check that the expected tags appear in the compiled tags database.

**Note:**
- The test will be skipped unless you pass `-m user_office` to pytest.
- This test is intended for development and CI environments where live API access is available and permitted.
- For most development, the unit tests (which do not require live API access) are sufficient.
