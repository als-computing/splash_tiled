from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from textwrap import shorten
from time import perf_counter
from typing import Any

import httpx
import typer

DEFAULT_API_URL = "https://als-esaf.als.lbl.gov/EsafInformation/GetEsaf"
DEFAULT_STAFF_API_URL = "https://alsusweb.lbl.gov/GetStaffByBeamline/"
DEFAULT_PROPOSALS_BY_BL_URL = "https://alsusweb.lbl.gov/ALSUserProposalsByBL/"


class Beamline(StrEnum):
    BL_1_4 = "1.4"
    # BL_2_0_1 = "2.0.1"
    BL_2_1 = "2.1"
    BL_2_4 = "2.4"
    BL_3_2_1 = "3.2.1"
    BL_3_3_1 = "3.3.1"
    BL_3_3_2 = "3.3.2"
    BL_4_0_2 = "4.0.2"
    BL_4_0_3 = "4.0.3"
    BL_4_2_2 = "4.2.2"
    # BL_5_0_1 = "5.0.1"
    # BL_5_0_2 = "5.0.2"
    # BL_5_0_3 = "5.0.3"
    BL_5_3_2_1 = "5.3.2.1"
    BL_5_3_2_2 = "5.3.2.2"
    BL_5_4 = "5.4"
    BL_6_0_1 = "6.0.1"
    BL_6_0_2 = "6.0.2"
    BL_6_1_2 = "6.1.2"
    BL_6_3_1 = "6.3.1"
    BL_6_3_2 = "6.3.2"
    BL_7_0_1_1 = "7.0.1.1"
    BL_7_0_1_2 = "7.0.1.2"
    BL_7_0_2 = "7.0.2"
    BL_7_3_1 = "7.3.1"
    BL_7_3_3 = "7.3.3"
    BL_8_0_1 = "8.0.1"
    # BL_8_2_1 = "8.2.1"
    # BL_8_2_2 = "8.2.2"
    # BL_8_3_1 = "8.3.1"
    BL_8_3_2 = "8.3.2"
    BL_9_0_1 = "9.0.1"
    BL_9_0_2 = "9.0.2"
    BL_9_3_1 = "9.3.1"
    BL_9_3_2 = "9.3.2"
    BL_10_0_1 = "10.0.1"
    BL_10_3_2 = "10.3.2"
    BL_11_0_1_1 = "11.0.1.1"
    BL_11_0_1_2 = "11.0.1.2"
    BL_11_0_2_1 = "11.0.2.1"
    BL_11_0_2_2 = "11.0.2.2"
    BL_11_3_1 = "11.3.1"
    # BL_11_3_2 = "11.3.2"
    BL_12_0_1 = "12.0.1"
    BL_12_0_2 = "12.0.2"
    BL_12_2_1 = "12.2.1"
    BL_12_2_2 = "12.2.2"
    BL_12_3_1 = "12.3.1"
    BL_12_3_2 = "12.3.2"


ALL_BEAMLINES = [beamline.value for beamline in Beamline]

app = typer.Typer(
    help="Fetch ESAFs for one or more ALS beamlines and store them in SQLite.",
    add_completion=False,
)


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def user_key(person: dict[str, Any]) -> str:
    orcid = normalize_text(person.get("Orcid"))
    if orcid is not None:
        return f"orcid:{orcid}"

    name = normalize_text(person.get("Name"))
    if name:
        return f"name:{name.casefold()}"

    raise ValueError("Cannot derive a stable user key from empty participant data")


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS beamline (
            name TEXT PRIMARY KEY,
            last_synced_at TEXT NOT NULL,
            esaf_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user (
            user_key TEXT PRIMARY KEY,
            name TEXT,
            orcid TEXT
        );

        CREATE TABLE IF NOT EXISTS esaf (
            esaf_id INTEGER PRIMARY KEY,
            beamline_name TEXT NOT NULL,
            esaf_friendly_id TEXT,
            proposal_id INTEGER,
            proposal_friendly_id TEXT,
            status TEXT,
            title TEXT,
            description TEXT,
            version INTEGER,
            pi_user_key TEXT,
            exp_lead_user_key TEXT,
            is_export_controlled TEXT,
            materials_json TEXT NOT NULL,
            scheduled_events_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (beamline_name) REFERENCES beamline(name),
            FOREIGN KEY (pi_user_key) REFERENCES user(user_key),
            FOREIGN KEY (exp_lead_user_key) REFERENCES user(user_key)
        );

        CREATE TABLE IF NOT EXISTS esaf_user (
            esaf_id INTEGER NOT NULL,
            user_key TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (esaf_id, user_key, role),
            FOREIGN KEY (esaf_id) REFERENCES esaf(esaf_id) ON DELETE CASCADE,
            FOREIGN KEY (user_key) REFERENCES user(user_key),
            CHECK (role IN ('participant', 'pi', 'exp_lead'))
        );

        CREATE TABLE IF NOT EXISTS beamline_staff_user (
            beamline_name TEXT NOT NULL,
            user_name TEXT NOT NULL,
            PRIMARY KEY (beamline_name, user_name)
        );

        CREATE TABLE IF NOT EXISTS proposal (
            proposal_friendly_id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proposal_user (
            proposal_friendly_id TEXT NOT NULL,
            user_key TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (proposal_friendly_id, user_key, role),
            FOREIGN KEY (proposal_friendly_id) REFERENCES proposal(proposal_friendly_id) ON DELETE CASCADE,
            FOREIGN KEY (user_key) REFERENCES user(user_key),
            CHECK (role IN ('pi', 'exp_lead'))
        );

        CREATE INDEX IF NOT EXISTS idx_esaf_beamline_name
        ON esaf (beamline_name);

        CREATE INDEX IF NOT EXISTS idx_esaf_proposal_id
        ON esaf (proposal_id);

        CREATE INDEX IF NOT EXISTS idx_esaf_proposal_friendly_id
        ON esaf (proposal_friendly_id);

        CREATE INDEX IF NOT EXISTS idx_esaf_beamline_proposal_id
        ON esaf (beamline_name, proposal_id);
        """)


def fetch_esafs(
    client: httpx.Client,
    beamline: str,
    api_url: str,
) -> list[dict[str, Any]]:
    typer.echo(f"Fetching {beamline}...")
    response = client.get(api_url, params={"bl": beamline})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(
            f"Expected list response for beamline {beamline}, got {type(payload)!r}"
        )
    return payload


def format_http_error(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        request = error.request
        return f"url={request.url} status={response.status_code}"

    request = error.request
    url = request.url if request is not None else "<unknown>"
    return f"url={url} message={error}"


def print_http_error(beamline: str, error: httpx.HTTPError) -> str:
    message = format_http_error(error)
    typer.echo(
        f"HTTP error for {beamline}: {message}",
        err=True,
    )
    return message


def collect_esaf_user_keys(esaf: dict[str, Any]) -> set[str]:
    user_keys: set[str] = set()
    for role_key in ("PI", "ExpLead"):
        person = esaf.get(role_key) or {}
        if person:
            user_keys.add(user_key(person))

    for participant in esaf.get("Participants") or []:
        user_keys.add(user_key(participant))

    return user_keys


def format_table(
    rows: list[dict[str, str]],
    headers: list[str],
    keys: list[str],
) -> str:
    widths = {
        header: max(
            len(header),
            max(
                (len(shorten(row[key], width=80, placeholder="...")) for row in rows),
                default=0,
            ),
        )
        for header, key in zip(headers, keys, strict=True)
    }

    def format_row(values: list[str]) -> str:
        return " | ".join(
            value.ljust(widths[header])
            for header, value in zip(headers, values, strict=True)
        )

    lines = [format_row(headers)]
    lines.append("-+-".join("-" * widths[header] for header in headers))
    for row in rows:
        values = [shorten(row[key], width=80, placeholder="...") for key in keys]
        lines.append(format_row(values))
    return "\n".join(lines)


def format_report_table(rows: list[dict[str, str]]) -> str:
    return format_table(
        rows,
        headers=["Beamline", "ESAFs", "New ESAFs", "Users", "New Users", "Error"],
        keys=["beamline", "esafs", "new_esafs", "users", "new_users", "error"],
    )


def format_proposals_report_table(rows: list[dict[str, str]]) -> str:
    return format_table(
        rows,
        headers=["Beamline", "Proposals", "New Proposals", "New Users", "Error"],
        keys=["beamline", "proposals", "new_proposals", "new_users", "error"],
    )


def print_report(rows: list[dict[str, str]], elapsed_seconds: float) -> None:
    if not rows:
        return

    typer.echo("\nBeamline sync report:")
    typer.echo(format_report_table(rows))
    typer.echo(f"Total time: {elapsed_seconds:.2f} seconds")


def print_proposals_report(rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    typer.echo("\nProposal sync report:")
    typer.echo(format_proposals_report_table(rows))


def fetch_beamline_staff(
    client: httpx.Client,
    api_url: str = DEFAULT_STAFF_API_URL,
) -> list[dict[str, Any]]:
    """Fetch all beamline staff from the ALS staff API.

    Returns the raw list of ``{"Beamline": ..., "Staff": [...]}`` records.
    """
    response = client.get(api_url, params={"bl": "all"})
    response.raise_for_status()
    payload = response.json()
    # API returns {"Beamlines": [...]} wrapper
    if isinstance(payload, dict) and "Beamlines" in payload:
        payload = payload["Beamlines"]
    if not isinstance(payload, list):
        raise ValueError(
            f"Expected list response from staff API, got {type(payload)!r}"
        )
    return payload


def get_beamline_staff_groups(
    staff_data: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Build a mapping of beamline name -> list of member ORCIDs.

    Every person who appears in a beamline's Staff list is included as a
    member of that beamline's group, identified by their ORCID.
    Entries without a usable ORCID are skipped.
    """
    groups: dict[str, list[str]] = {}
    for entry in staff_data:
        beamline_name = normalize_text(entry.get("Beamline"))
        if not beamline_name:
            continue
        members: set[str] = set()
        for person in entry.get("Staff") or []:
            orcid = normalize_text(person.get("ORCID"))
            if orcid:
                members.add(orcid)
        groups[beamline_name] = sorted(members)
    return groups


def upsert_staff_users(
    connection: sqlite3.Connection,
    staff_data: list[dict[str, Any]],
) -> None:
    for entry in staff_data:
        for person in entry.get("Staff") or []:
            orcid = normalize_text(person.get("ORCID"))
            if not orcid:
                continue
            connection.execute(
                """
                INSERT INTO user (user_key, name, orcid)
                VALUES (?, ?, ?)
                ON CONFLICT(user_key) DO UPDATE SET
                    name = excluded.name,
                    orcid = excluded.orcid
                """,
                (f"orcid:{orcid}", normalize_text(person.get("Name")), orcid),
            )


def sync_beamline_staff_groups(
    connection: sqlite3.Connection,
    groups: dict[str, list[str]],
) -> None:
    rows = [
        (beamline_name, user_name)
        for beamline_name, members in groups.items()
        for user_name in members
    ]
    connection.execute("DELETE FROM beamline_staff_user")
    connection.executemany(
        "INSERT INTO beamline_staff_user (beamline_name, user_name) VALUES (?, ?)",
        sorted(set(rows)),
    )


_INVALID_ESCAPE_RE = re.compile(r'\\([^"\\/bfnrtu\n])')


def _fix_json_escapes(text: str) -> str:
    """Replace invalid JSON escape sequences with escaped backslashes."""
    return _INVALID_ESCAPE_RE.sub(r"\\\\\1", text)


def fetch_proposals_by_beamline(
    client: httpx.Client,
    beamline: str,
    api_url: str,
) -> list[dict[str, Any]]:
    """Return all proposal records for a beamline."""
    response = client.get(api_url, params={"bl": beamline}, timeout=120.0)
    response.raise_for_status()
    try:
        data = response.json()
    except json.JSONDecodeError:
        data = json.loads(_fix_json_escapes(response.text))
    return [p for p in (data.get("Proposals") or []) if p.get("ExpID")]


def sync_proposal(
    connection: sqlite3.Connection,
    proposal_data: dict[str, Any],
    synced_at: str,
) -> bool:
    proposal_friendly_id = normalize_text(proposal_data.get("ExpID"))
    if not proposal_friendly_id:
        raise ValueError("Proposal payload is missing ExpID")

    is_new = not connection.execute(
        "SELECT 1 FROM proposal WHERE proposal_friendly_id = ?", (proposal_friendly_id,)
    ).fetchone()

    connection.execute(
        """
        INSERT INTO proposal (proposal_friendly_id, title, abstract, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(proposal_friendly_id) DO UPDATE SET
            abstract = excluded.abstract,
            updated_at = excluded.updated_at
        """,
        (
            proposal_friendly_id,
            None,
            normalize_text(proposal_data.get("Abstract")),
            synced_at,
        ),
    )
    return is_new


def sync_proposals(
    connection: sqlite3.Connection,
    client: httpx.Client,
    beamlines: list[str],
    proposals_by_bl_url: str,
    synced_at: str,
) -> tuple[int, int]:
    beamline_proposals: dict[str, list[dict[str, Any]]] = {}
    beamline_errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                fetch_proposals_by_beamline, client, bl, proposals_by_bl_url
            ): bl
            for bl in beamlines
        }
        for future in as_completed(futures):
            bl = futures[future]
            try:
                proposals = future.result()
                beamline_proposals[bl] = proposals
                typer.echo(f"Stored {len(proposals)} proposals for {bl}")
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    msg = format_http_error(error)
                    beamline_errors[bl] = msg
                    typer.echo(f"Error fetching proposals for {bl}: {msg}", err=True)
            except (httpx.HTTPError, ValueError) as error:
                beamline_errors[bl] = str(error)
                typer.echo(f"Error fetching proposals for {bl}: {error}", err=True)

    # Deduplicate across beamlines, write to DB
    seen: set[str] = set()
    new_count = 0
    for proposals in beamline_proposals.values():
        for proposal_data in proposals:
            pid = proposal_data.get("ExpID", "")
            if pid in seen:
                continue
            seen.add(pid)
            try:
                if sync_proposal(connection, proposal_data, synced_at):
                    new_count += 1
            except ValueError as error:
                typer.echo(f"Error syncing proposal {pid}: {error}", err=True)

    total = len(seen)
    typer.echo(
        f"Synced {total} proposals ({new_count} new) across {len(beamline_proposals)} beamlines"
    )

    report_rows = []
    for bl in sorted(beamlines):
        proposals = beamline_proposals.get(bl, [])
        report_rows.append(
            {
                "beamline": bl,
                "proposals": str(len(proposals)),
                "new_proposals": "",
                "new_users": "",
                "error": beamline_errors.get(bl, ""),
            }
        )
    print_proposals_report(report_rows)

    return total, new_count


def get_beamline_staff_group_map(
    connection: sqlite3.Connection,
) -> dict[str, list[str]]:
    rows = connection.execute("""
        SELECT beamline_name, user_name
        FROM beamline_staff_user
        ORDER BY beamline_name, user_name
        """).fetchall()

    groups: dict[str, list[str]] = {}
    for beamline_name, user_name in rows:
        groups.setdefault(beamline_name, []).append(user_name)
    return groups


def get_esaf_orcid_map(connection: sqlite3.Connection) -> dict[str, list[str]]:
    rows = connection.execute("""
        SELECT DISTINCT e.esaf_friendly_id, u.orcid
        FROM esaf AS e
        LEFT JOIN esaf_user AS eu ON eu.esaf_id = e.esaf_id
        LEFT JOIN user AS u ON u.user_key = eu.user_key
        WHERE e.esaf_friendly_id IS NOT NULL
        ORDER BY e.esaf_friendly_id, u.orcid
        """).fetchall()

    orcid_map: dict[str, list[str]] = {}
    for esaf_friendly_id, orcid in rows:
        values = orcid_map.setdefault(esaf_friendly_id, [])
        if orcid is not None:
            values.append(orcid)
    return orcid_map


def get_proposal_orcid_map(connection: sqlite3.Connection) -> dict[str, list[str]]:
    rows = connection.execute("""
        SELECT DISTINCT proposal_friendly_id, orcid FROM (
            SELECT pu.proposal_friendly_id, u.orcid
            FROM proposal_user pu
            JOIN user u ON u.user_key = pu.user_key
            WHERE u.orcid IS NOT NULL

            UNION

            SELECT e.proposal_friendly_id, u.orcid
            FROM esaf e
            JOIN esaf_user eu ON eu.esaf_id = e.esaf_id
            JOIN user u ON u.user_key = eu.user_key
            WHERE e.proposal_friendly_id IS NOT NULL
            AND u.orcid IS NOT NULL
        )
        ORDER BY proposal_friendly_id, orcid
        """).fetchall()

    orcid_map: dict[str, list[str]] = {}
    for proposal_friendly_id, orcid in rows:
        orcid_map.setdefault(proposal_friendly_id, []).append(orcid)
    return orcid_map


def get_beamlines_by_proposal(connection: sqlite3.Connection) -> dict[str, list[str]]:
    rows = connection.execute("""
        SELECT DISTINCT proposal_friendly_id, beamline_name
        FROM esaf
        WHERE proposal_friendly_id IS NOT NULL
        AND beamline_name IS NOT NULL
        ORDER BY proposal_friendly_id, beamline_name
        """).fetchall()

    beamlines_by_proposal: dict[str, list[str]] = {}
    for proposal_friendly_id, beamline_name in rows:
        beamlines_by_proposal.setdefault(proposal_friendly_id, []).append(beamline_name)
    return beamlines_by_proposal


def get_esaf_friendly_ids(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute("""
        SELECT DISTINCT esaf_friendly_id
        FROM esaf
        WHERE esaf_friendly_id IS NOT NULL
        ORDER BY esaf_friendly_id
        """).fetchall()

    return [esaf_friendly_id for (esaf_friendly_id,) in rows]


def get_esaf_friendly_ids_by_beamline(
    connection: sqlite3.Connection,
) -> dict[str, list[str]]:
    rows = connection.execute("""
        SELECT beamline_name, esaf_friendly_id
        FROM esaf
        WHERE beamline_name IS NOT NULL
        AND esaf_friendly_id IS NOT NULL
        ORDER BY beamline_name, esaf_friendly_id
        """).fetchall()

    esaf_ids_by_beamline: dict[str, list[str]] = {}
    for beamline_name, esaf_friendly_id in rows:
        esaf_ids_by_beamline.setdefault(beamline_name, []).append(esaf_friendly_id)
    return esaf_ids_by_beamline


def user_exists(connection: sqlite3.Connection, key: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM user WHERE user_key = ?",
        (key,),
    ).fetchone()
    return row is not None


def esaf_exists(connection: sqlite3.Connection, esaf_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM esaf WHERE esaf_id = ?",
        (esaf_id,),
    ).fetchone()
    return row is not None


def upsert_user(
    connection: sqlite3.Connection, person: dict[str, Any]
) -> tuple[str, bool]:
    key = user_key(person)
    is_new = not user_exists(connection, key)
    connection.execute(
        """
        INSERT INTO user (user_key, name, orcid)
        VALUES (?, ?, ?)
        ON CONFLICT(user_key) DO UPDATE SET
            name = excluded.name,
            orcid = excluded.orcid
        """,
        (
            key,
            normalize_text(person.get("Name")),
            normalize_text(person.get("Orcid")),
        ),
    )
    return key, is_new


def sync_esaf(
    connection: sqlite3.Connection,
    beamline: str,
    esaf: dict[str, Any],
    synced_at: str,
) -> tuple[bool, set[str]]:
    pi = esaf.get("PI") or {}
    exp_lead = esaf.get("ExpLead") or {}
    participants = esaf.get("Participants") or []
    esaf_id = normalize_int(esaf.get("EsafId"))
    if esaf_id is None:
        raise ValueError("ESAF payload is missing EsafId")
    is_new_esaf = not esaf_exists(connection, esaf_id)
    new_user_keys: set[str] = set()

    pi_key = None
    if pi:
        pi_key, pi_is_new = upsert_user(connection, pi)
        if pi_is_new:
            new_user_keys.add(pi_key)

    exp_lead_key = None
    if exp_lead:
        exp_lead_key, exp_lead_is_new = upsert_user(connection, exp_lead)
        if exp_lead_is_new:
            new_user_keys.add(exp_lead_key)

    participant_keys: list[str] = []
    for participant in participants:
        participant_key, participant_is_new = upsert_user(connection, participant)
        participant_keys.append(participant_key)
        if participant_is_new:
            new_user_keys.add(participant_key)

    connection.execute(
        """
        INSERT INTO esaf (
            esaf_id,
            beamline_name,
            esaf_friendly_id,
            proposal_id,
            proposal_friendly_id,
            status,
            title,
            description,
            version,
            pi_user_key,
            exp_lead_user_key,
            is_export_controlled,
            materials_json,
            scheduled_events_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(esaf_id) DO UPDATE SET
            beamline_name = excluded.beamline_name,
            esaf_friendly_id = excluded.esaf_friendly_id,
            proposal_id = excluded.proposal_id,
            proposal_friendly_id = excluded.proposal_friendly_id,
            status = excluded.status,
            title = excluded.title,
            description = excluded.description,
            version = excluded.version,
            pi_user_key = excluded.pi_user_key,
            exp_lead_user_key = excluded.exp_lead_user_key,
            is_export_controlled = excluded.is_export_controlled,
            materials_json = excluded.materials_json,
            scheduled_events_json = excluded.scheduled_events_json,
            updated_at = excluded.updated_at
        """,
        (
            esaf_id,
            beamline,
            normalize_text(esaf.get("EsafFriendlyId")),
            normalize_int(esaf.get("ProposalId")),
            normalize_text(esaf.get("ProposalFriendlyId")),
            normalize_text(esaf.get("Status")),
            normalize_text(esaf.get("Title")),
            normalize_text(esaf.get("Description")),
            normalize_int(esaf.get("Version")),
            pi_key,
            exp_lead_key,
            normalize_text(esaf.get("IsExportControlled")),
            json.dumps(esaf.get("Materials") or []),
            json.dumps(esaf.get("ScheduledEvents") or []),
            synced_at,
        ),
    )

    connection.execute("DELETE FROM esaf_user WHERE esaf_id = ?", (esaf_id,))

    rows: set[tuple[int, str, str]] = set()
    if pi_key:
        rows.add((esaf_id, pi_key, "pi"))
    if exp_lead_key:
        rows.add((esaf_id, exp_lead_key, "exp_lead"))
    rows.update(
        (esaf_id, participant_key, "participant")
        for participant_key in participant_keys
    )

    connection.executemany(
        "INSERT INTO esaf_user (esaf_id, user_key, role) VALUES (?, ?, ?)",
        sorted(rows),
    )
    return is_new_esaf, new_user_keys


def sync_beamline(
    connection: sqlite3.Connection,
    beamline: str,
    esafs: Iterable[dict[str, Any]],
    synced_at: str,
) -> tuple[int, int, int, int]:
    items = list(esafs)
    new_esaf_count = 0
    new_user_keys: set[str] = set()
    total_user_keys: set[str] = set()
    connection.execute(
        """
        INSERT INTO beamline (name, last_synced_at, esaf_count)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            last_synced_at = excluded.last_synced_at,
            esaf_count = excluded.esaf_count
        """,
        (beamline, synced_at, len(items)),
    )
    with typer.progressbar(items, label=f"Syncing {beamline}") as progress:
        for esaf in progress:
            total_user_keys.update(collect_esaf_user_keys(esaf))
            is_new_esaf, esaf_new_user_keys = sync_esaf(
                connection, beamline, esaf, synced_at
            )
            new_esaf_count += int(is_new_esaf)
            new_user_keys.update(esaf_new_user_keys)
    return len(items), new_esaf_count, len(total_user_keys), len(new_user_keys)


def run(
    beamlines: list[str],
    db_path: Path,
    api_url: str = DEFAULT_API_URL,
    proposals_by_bl_url: str = DEFAULT_PROPOSALS_BY_BL_URL,
    timeout: float = 30.0,
) -> int:
    start_time = perf_counter()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    failed_beamlines: list[str] = []
    report_rows: list[dict[str, str]] = []
    interrupted = False

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        with sqlite3.connect(db_path) as connection:
            ensure_schema(connection)
            try:
                staff_data = fetch_beamline_staff(client)
                staff_groups = get_beamline_staff_groups(staff_data)
                sync_beamline_staff_groups(connection, staff_groups)
                upsert_staff_users(connection, staff_data)
                typer.echo(
                    "Stored beamline staff groups " f"for {len(staff_groups)} beamlines"
                )
            except httpx.HTTPError as error:
                typer.echo(
                    f"Failed to fetch beamline staff groups: "
                    f"{format_http_error(error)}",
                    err=True,
                )
            try:
                with typer.progressbar(
                    beamlines, label="Beamlines"
                ) as beamline_progress:
                    for beamline in beamline_progress:
                        synced_at = utc_now()
                        try:
                            esafs = fetch_esafs(
                                client, beamline=beamline, api_url=api_url
                            )
                        except httpx.HTTPError as error:
                            error_message = print_http_error(beamline, error)
                            failed_beamlines.append(beamline)
                            report_rows.append(
                                {
                                    "beamline": beamline,
                                    "esafs": "0",
                                    "new_esafs": "0",
                                    "users": "0",
                                    "new_users": "0",
                                    "error": error_message,
                                }
                            )
                            continue
                        total, new_esafs, total_users, new_users = sync_beamline(
                            connection,
                            beamline=beamline,
                            esafs=esafs,
                            synced_at=synced_at,
                        )
                        typer.echo(f"Stored {total} ESAFs for {beamline}")
                        typer.echo(
                            f"New for {beamline}: {new_esafs} ESAFs, {new_users} users"
                        )
                        report_rows.append(
                            {
                                "beamline": beamline,
                                "esafs": str(total),
                                "new_esafs": str(new_esafs),
                                "users": str(total_users),
                                "new_users": str(new_users),
                                "error": "",
                            }
                        )
                synced_at = utc_now()
                sync_proposals(
                    connection, client, beamlines, proposals_by_bl_url, synced_at
                )
            except KeyboardInterrupt:
                interrupted = True
            finally:
                elapsed_seconds = perf_counter() - start_time
                print_report(report_rows, elapsed_seconds)

    if failed_beamlines:
        typer.echo(
            f"Failed beamlines: {', '.join(failed_beamlines)}",
            err=True,
        )
        return 1

    if interrupted:
        typer.echo("Sync interrupted by user.", err=True)
        return 130

    return 0


def resolve_beamlines(selected: list[Beamline], sync_all: bool) -> list[str]:
    if sync_all:
        return ALL_BEAMLINES

    if selected:
        return [beamline.value for beamline in selected]

    raise typer.BadParameter(
        "Provide at least one --beamline value or pass --all.",
        param_hint="--beamline/--all",
    )


@app.command()
def cli(
    beamline: list[Beamline] = typer.Option(
        [],
        "--beamline",
        help="Beamline to fetch. Repeat for multiple beamlines.",
    ),
    sync_all: bool = typer.Option(
        False,
        "--all",
        help="Sync every beamline defined in the Beamline enum.",
    ),
    db_path: Path = typer.Option(
        Path("esafs.db"),
        "--db-path",
        help="SQLite database path. Defaults to ./esafs.db.",
    ),
    api_url: str = typer.Option(
        DEFAULT_API_URL,
        "--api-url",
        help="ESAF API base URL.",
    ),
    proposals_by_bl_url: str = typer.Option(
        DEFAULT_PROPOSALS_BY_BL_URL,
        "--proposals-by-bl-url",
        help="Proposals-by-beamline API base URL.",
    ),
    timeout: float = typer.Option(
        30.0,
        "--timeout",
        help="HTTP timeout in seconds.",
    ),
) -> None:
    resolved_beamlines = resolve_beamlines(beamline, sync_all)
    raise SystemExit(
        run(
            beamlines=resolved_beamlines,
            db_path=db_path,
            api_url=api_url,
            proposals_by_bl_url=proposals_by_bl_url,
            timeout=timeout,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
