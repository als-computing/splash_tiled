import sqlite3
from typing import Any

from splash_tiled.access_control.user_office import (
    ensure_schema,
    get_beamline_staff_group_map,
    get_beamline_staff_groups,
    get_esaf_orcid_map,
    sync_beamline,
    sync_beamline_staff_groups,
    user_key,
)


def test_user_key_uses_orcid() -> None:
    person = {
        "Name": "Scientist Name",
        "Orcid": "0000-0001-2345-6789",
    }

    assert user_key(person) == "orcid:0000-0001-2345-6789"


def test_user_key_falls_back_to_name() -> None:
    person = {
        "Name": "Scientist Name",
        "Orcid": None,
    }

    assert user_key(person) == "name:scientist name"


def test_sync_beamline_persists_normalized_records() -> None:
    esaf = {
        "Beamline": "12.3.2",
        "Description": (
            "We will bring quantum material crystals and measure their "
            "properties under applied strain"
        ),
        "EsafFriendlyId": "ALS-13362-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "CHu2@lbl.gov",
            "LbnlId": "070285",
            "Name": "Cheng Hu",
            "Orcid": "0000-0003-2335-7806",
        },
        "IsExportControlled": "No",
        "Materials": ["Chemicals, including nanomaterials"],
        "PI": {
            "Alsid": 11525,
            "Email": "erotenberg@lbl.gov",
            "LbnlId": "275451",
            "Name": "Eli Rotenberg",
            "Orcid": "0000-0002-3979-8844",
        },
        "Participants": [
            {
                "Alsid": 83512,
                "Email": "CHu2@lbl.gov",
                "LbnlId": "070285",
                "Name": "Cheng Hu",
                "Orcid": "0000-0003-2335-7806",
            },
            {
                "Alsid": 11525,
                "Email": "erotenberg@lbl.gov",
                "LbnlId": "275451",
                "Name": "Eli Rotenberg",
                "Orcid": "0000-0002-3979-8844",
            },
        ],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(":memory:") as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

        beamline_row = connection.execute(
            "SELECT name, esaf_count FROM beamline"
        ).fetchone()
        assert beamline_row == ("12.3.2", 1)

        esaf_row = connection.execute(
            "SELECT beamline_name, pi_user_key, exp_lead_user_key "
            "FROM esaf WHERE esaf_id = 36017"
        ).fetchone()
        assert esaf_row == (
            "12.3.2",
            "orcid:0000-0002-3979-8844",
            "orcid:0000-0003-2335-7806",
        )

        user_count = connection.execute("SELECT COUNT(*) FROM user").fetchone()[0]
        assert user_count == 2

        role_rows = connection.execute(
            "SELECT user_key, role FROM esaf_user WHERE esaf_id = 36017 "
            "ORDER BY role, user_key"
        ).fetchall()
        assert role_rows == [
            ("orcid:0000-0003-2335-7806", "exp_lead"),
            ("orcid:0000-0002-3979-8844", "participant"),
            ("orcid:0000-0003-2335-7806", "participant"),
            ("orcid:0000-0002-3979-8844", "pi"),
        ]


def test_get_esaf_orcid_map_returns_distinct_orcids_per_esaf() -> None:
    esaf = {
        "Beamline": "12.3.2",
        "Description": "Microdiffraction of ARPES samples",
        "EsafFriendlyId": "ALS-13362-001",
        "EsafId": 36017,
        "ExpLead": {
            "Alsid": 83512,
            "Email": "CHu2@lbl.gov",
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
        "Participants": [
            {
                "Alsid": 83512,
                "Email": "CHu2@lbl.gov",
                "LbnlId": "070285",
                "Name": "Cheng Hu",
                "Orcid": "0000-0003-2335-7806",
            },
            {
                "Alsid": 11525,
                "Email": "erotenberg@lbl.gov",
                "LbnlId": "275451",
                "Name": "Eli Rotenberg",
                "Orcid": "0000-0002-3979-8844",
            },
        ],
        "ProposalFriendlyId": "ALS-13362",
        "ProposalId": 19907,
        "ScheduledEvents": [],
        "Status": "Draft",
        "Title": "Microdiffraction of ARPES samples",
        "Version": 1,
    }

    with sqlite3.connect(":memory:") as connection:
        ensure_schema(connection)
        sync_beamline(
            connection,
            beamline="12.3.2",
            esafs=[esaf],
            synced_at="2026-04-04T00:00:00+00:00",
        )

        assert get_esaf_orcid_map(connection) == {
            "ALS-13362-001": [
                "0000-0002-3979-8844",
                "0000-0003-2335-7806",
            ]
        }


def test_sync_beamline_staff_groups_persists_orcid_members() -> None:
    staff_payload: list[dict[str, Any]] = [
        {
            "Beamline": "9.3.2",
            "Staff": [
                {"ORCID": "0000-0001-2345-6789"},
                {"ORCID": "0000-0002-3456-7890"},
                {"ORCID": "0000-0001-2345-6789"},  # duplicate
                {"ORCID": None},  # no orcid — skipped
            ],
        },
        {
            "Beamline": "12.3.2",
            "Staff": [
                {"ORCID": "0000-0003-4567-8901"},
            ],
        },
    ]

    groups = get_beamline_staff_groups(staff_payload)

    with sqlite3.connect(":memory:") as connection:
        ensure_schema(connection)
        sync_beamline_staff_groups(connection, groups)

        assert get_beamline_staff_group_map(connection) == {
            "12.3.2": ["0000-0003-4567-8901"],
            "9.3.2": ["0000-0001-2345-6789", "0000-0002-3456-7890"],
        }
