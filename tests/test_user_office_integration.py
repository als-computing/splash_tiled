import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml  # type: ignore[import-untyped]

from splash_tiled.access_control.tiled_tags import compile_tags
from splash_tiled.access_control.user_office import (
    DEFAULT_API_URL,
    ensure_schema,
    fetch_beamline_staff,
    fetch_esafs,
    get_beamline_staff_groups,
    sync_beamline,
    sync_beamline_staff_groups,
)


@pytest.mark.user_office
def test_live_user_office_sync_compiles_stub_entries(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stub_path = (
        repo_root
        / "src"
        / "splash_tiled"
        / "access_control"
        / "tag_definitions_stub.yaml"
    )

    esaf_db_path = tmp_path / "esafs.db"
    generated_yaml_path = tmp_path / "tag_definitions.generated.yml"
    compiled_db_path = tmp_path / "compiled_tags.db"

    beamline = "12.3.2"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        try:
            staff_payload = fetch_beamline_staff(client)
            esafs = fetch_esafs(client, beamline=beamline, api_url=DEFAULT_API_URL)
        except httpx.HTTPError as exc:
            pytest.skip(f"User Office API unavailable: {exc}")

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline_staff_groups(
            connection,
            get_beamline_staff_groups(staff_payload),
        )
        sync_beamline(
            connection,
            beamline=beamline,
            esafs=esafs,
            synced_at="2026-04-28T00:00:00+00:00",
        )

    compile_tags(
        output_sqlite_path=compiled_db_path,
        esaf_db_path=esaf_db_path,
        tag_definitions_path=stub_path,
        generated_tag_definitions_path=generated_yaml_path,
    )

    stub = yaml.safe_load(stub_path.read_text(encoding="utf-8"))
    data_admin_users = [
        item["name"]
        for item in ((stub.get("tags") or {}).get("data_admin") or {}).get("users", [])
    ]
    facility_admin_scopes = set(
        ((stub.get("roles") or {}).get("facility_admin") or {}).get("scopes", [])
    )
    facility_user_scopes = set(
        ((stub.get("roles") or {}).get("facility_user") or {}).get("scopes", [])
    )

    with sqlite3.connect(compiled_db_path) as connection:
        cursor = connection.cursor()

        cursor.execute("SELECT id FROM tags WHERE name = 'data_admin'")
        data_admin_row = cursor.fetchone()
        assert data_admin_row is not None
        data_admin_tag_id = data_admin_row[0]

        cursor.execute("SELECT name FROM scopes")
        all_scopes = {row[0] for row in cursor.fetchall()}
        assert facility_admin_scopes.issubset(all_scopes)
        assert facility_user_scopes.issubset(all_scopes)

        for user_name in data_admin_users:
            cursor.execute(
                """
                SELECT s.name FROM tags_users_scopes tus
                JOIN users u ON u.id = tus.user_id
                JOIN scopes s ON s.id = tus.scope_id
                WHERE tus.tag_id = ? AND u.name = ?
                """,
                (data_admin_tag_id, user_name),
            )
            user_scopes = {row[0] for row in cursor.fetchall()}
            assert facility_admin_scopes.issubset(user_scopes)
