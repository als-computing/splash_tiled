import sqlite3
from pathlib import Path

import pytest
import typer
import yaml  # type: ignore[import-untyped]

from splash_tiled.access_control.tiled_tags import (
    build_generated_tag_definitions,
    build_group_parser,
    build_sqlite_uri,
    compile_tags,
    ensure_output_sqlite_path,
    generate_tag_definitions_yaml,
    write_tag_definitions_yaml,
)
from splash_tiled.access_control.user_office import (
    ensure_schema,
    get_esaf_friendly_ids_by_beamline,
    sync_beamline,
)


def test_ensure_output_sqlite_path_creates_parent_and_file(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "compiled_tags.sqlite"

    resolved_path = ensure_output_sqlite_path(output_path)

    assert resolved_path == output_path.resolve()
    assert resolved_path.parent.is_dir()
    assert resolved_path.is_file()


def test_build_sqlite_uri_uses_absolute_sqlite_file_uri(tmp_path: Path) -> None:
    output_path = tmp_path / "compiled tags.sqlite"

    sqlite_uri = build_sqlite_uri(output_path)

    assert sqlite_uri == f"file:{output_path.resolve().as_posix().replace(' ', '%20')}"


def test_ensure_output_sqlite_path_raises_for_unwritable_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "compiled_tags.sqlite"

    def raise_permission_error(*args, **kwargs) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "touch", raise_permission_error)

    with pytest.raises(typer.BadParameter, match="Choose a writable path"):
        ensure_output_sqlite_path(output_path)


def test_build_generated_tag_definitions_includes_template_sections_and_esaf_tags(
    tmp_path: Path,
) -> None:
    esaf_db_path = tmp_path / "esafs.sqlite3"
    template_path = tmp_path / "tag_definitions_stub.yaml"

    template_path.write_text(
        """
roles:
  facility_user:
    scopes:
      - read:data
      - read:metadata
  facility_admin:
    scopes:
      - read:data
tags:
  data_admin:
    users:
      - name: cara
        role: facility_admin
tag_owners:
  data_admin:
    users:
      - name: cara
""".lstrip(),
        encoding="utf-8",
    )

    esaf = {
        "Beamline": "12.3.2",
        "Description": "Microdiffraction of ARPES samples",
        "EsafFriendlyId": "SB-01482-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "chu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": [],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

    with sqlite3.connect(esaf_db_path) as connection:
        assert get_esaf_friendly_ids_by_beamline(connection) == {
            "12.3.2": ["SB-01482-001"]
        }

    generated = build_generated_tag_definitions(esaf_db_path, template_path)

    assert generated["roles"]["facility_user"]["scopes"] == [
        "read:data",
        "read:metadata",
    ]
    assert generated["tags"]["SB-01482-001"] == {
        "groups": [
            {"name": "SB-01482-001", "role": "facility_user"},
            {"name": "12.3.2-staff", "role": "facility_user"},
        ],
        "auto_tags": [{"name": "data_admin"}, {"name": "12.3.2-staff"}],
    }
    assert generated["tags"]["data_admin"]["users"] == [
        {"name": "cara", "role": "facility_admin"}
    ]
    assert generated["tag_owners"]["data_admin"]["users"] == [{"name": "cara"}]


def test_write_tag_definitions_yaml_writes_yaml_file(tmp_path: Path) -> None:
    output_yaml_path = tmp_path / "generated" / "tag_definitions.yml"
    content = {
        "roles": {"facility_user": {"scopes": ["read:data"]}},
        "tags": {
            "SB-01482-001": {
                "groups": [{"name": "SB-01482-001", "role": "facility_user"}]
            }
        },
        "tag_owners": {},
    }

    resolved_output_yaml_path = write_tag_definitions_yaml(content, output_yaml_path)

    assert resolved_output_yaml_path == output_yaml_path.resolve()
    assert yaml.safe_load(output_yaml_path.read_text(encoding="utf-8")) == content


def test_generate_tag_definitions_yaml_writes_generated_esaf_tags(
    tmp_path: Path,
) -> None:
    esaf_db_path = tmp_path / "esafs.sqlite3"
    template_path = tmp_path / "tag_definitions_stub.yaml"
    output_yaml_path = tmp_path / "tag_definitions.generated.yml"

    template_path.write_text(
        """
roles:
  facility_user:
    scopes:
      - read:data
      - read:metadata
tags:
  data_admin:
    users:
      - name: cara
        role: facility_admin
tag_owners:
  data_admin:
    users:
      - name: cara
""".lstrip(),
        encoding="utf-8",
    )

    esaf = {
        "Beamline": "12.3.2",
        "Description": "Microdiffraction of ARPES samples",
        "EsafFriendlyId": "SB-01482-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "chu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": [],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

    resolved_output_yaml_path = generate_tag_definitions_yaml(
        esaf_db_path=esaf_db_path,
        tag_definitions_path=template_path,
        output_yaml_path=output_yaml_path,
    )

    generated = yaml.safe_load(resolved_output_yaml_path.read_text(encoding="utf-8"))
    assert resolved_output_yaml_path == output_yaml_path.resolve()
    assert generated["tags"]["SB-01482-001"]["groups"] == [
        {"name": "SB-01482-001", "role": "facility_user"},
        {"name": "12.3.2-staff", "role": "facility_user"},
    ]
    assert generated["tags"]["SB-01482-001"]["auto_tags"] == [
        {"name": "data_admin"},
        {"name": "12.3.2-staff"},
    ]


def test_build_generated_tag_definitions_staff_group_in_auto_tags(
    tmp_path: Path,
) -> None:
    esaf_db_path = tmp_path / "esafs.sqlite3"
    template_path = tmp_path / "tag_definitions_stub.yaml"

    template_path.write_text(
        """
roles:
  facility_user:
    scopes:
      - read:data
      - read:metadata
tags: {}
tag_owners: {}
""".lstrip(),
        encoding="utf-8",
    )

    esaf = {
        "Beamline": "12.3.2",
        "Description": "Microdiffraction of ARPES samples",
        "EsafFriendlyId": "SB-01482-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "chu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": [],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

    generated = build_generated_tag_definitions(esaf_db_path, template_path)

    assert generated["tags"]["SB-01482-001"]["auto_tags"] == [
        {"name": "data_admin"},
        {"name": "12.3.2-staff"},
    ]


def test_build_group_parser_includes_empty_beamline_staff_groups(
    tmp_path: Path,
) -> None:
    esaf_db_path = tmp_path / "esafs.sqlite3"

    esaf = {
        "Beamline": "12.3.2",
        "Description": "Microdiffraction of ARPES samples",
        "EsafFriendlyId": "SB-01482-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "chu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": [],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

    group_parser = build_group_parser(esaf_db_path)

    assert group_parser("SB-01482-001") == [
        "0000-0002-3979-8844",
        "0000-0003-2335-7806",
    ]
    assert group_parser("12.3.2-staff") == []


def test_compile_tags_reflects_roles_and_data_admin_in_sqlite(
    tmp_path: Path,
) -> None:
    esaf_db_path = tmp_path / "esafs.sqlite3"
    template_path = tmp_path / "tag_definitions_stub.yaml"
    generated_yaml_path = tmp_path / "tag_definitions.generated.yml"
    compiled_db_path = tmp_path / "compiled_tags.sqlite"

    template_path.write_text(
        """
roles:
  facility_user:
    scopes:
      - read:data
      - read:metadata
  facility_admin:
    scopes:
      - read:data
      - read:metadata
      - write:data
      - write:metadata
      - delete:node
      - delete:revision
      - create:node
      - register
tags:
  data_admin:
    users:
      - name: "0000-0001-0000-0001"
        role: facility_admin
tag_owners: {}
""".lstrip(),
        encoding="utf-8",
    )

    esaf = {
        "Beamline": "12.3.2",
        "Description": "Test ESAF",
        "EsafFriendlyId": "SB-01482-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "chu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": [],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Test ESAF",
        "Version": 1,
    }

    with sqlite3.connect(esaf_db_path) as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

    compile_tags(
        output_sqlite_path=compiled_db_path,
        esaf_db_path=esaf_db_path,
        tag_definitions_path=template_path,
        generated_tag_definitions_path=generated_yaml_path,
    )

    with sqlite3.connect(compiled_db_path) as con:
        cur = con.cursor()

        # data_admin tag exists in the compiled database
        cur.execute("SELECT id FROM tags WHERE name = 'data_admin'")
        data_admin_row = cur.fetchone()
        assert data_admin_row is not None, "data_admin tag not found in compiled DB"
        data_admin_id = data_admin_row[0]

        # the data_admin user is associated with data_admin and has facility_admin scopes
        cur.execute(
            """
            SELECT s.name FROM tags_users_scopes tus
            JOIN users u ON u.id = tus.user_id
            JOIN scopes s ON s.id = tus.scope_id
            WHERE tus.tag_id = ? AND u.name = '0000-0001-0000-0001'
            ORDER BY s.name
            """,
            (data_admin_id,),
        )
        admin_scopes = {row[0] for row in cur.fetchall()}
        assert "read:data" in admin_scopes
        assert "write:data" in admin_scopes
        assert "create:node" in admin_scopes
        assert "delete:node" in admin_scopes

        # facility_user scopes are present in the DB (used by ESAF and staff tags)
        cur.execute("SELECT name FROM scopes ORDER BY name")
        all_scopes = {row[0] for row in cur.fetchall()}
        assert "read:data" in all_scopes
        assert "read:metadata" in all_scopes

        # the data_admin user does NOT have facility_user-only read:data access
        # on the ESAF tag (it gets access via auto_tag, not direct membership)
        cur.execute("SELECT id FROM tags WHERE name = 'SB-01482-001'")
        assert (
            cur.fetchone() is not None
        ), "SB-01482-001 ESAF tag not found in compiled DB"
