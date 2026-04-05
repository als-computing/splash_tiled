from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from textwrap import shorten
from time import perf_counter
from typing import Any

import httpx
import typer

DEFAULT_API_URL = "https://als-esaf.als.lbl.gov/EsafInformation/GetEsaf"


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


def normalize_email(value: Any) -> str | None:
    text = normalize_text(value)
    return text.lower() if text else None


def normalize_lbnl_id(value: Any) -> str | None:
    text = normalize_text(value)
    if text and text.lower() != "unknown":
        return text
    return None


def normalize_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def user_key(person: dict[str, Any]) -> str:
    alsid = normalize_int(person.get("Alsid"))
    if alsid is not None:
        return f"alsid:{alsid}"

    email = normalize_email(person.get("Email"))
    if email:
        return f"email:{email}"

    lbnl_id = normalize_lbnl_id(person.get("LbnlId"))
    if lbnl_id:
        return f"lbnl:{lbnl_id}"

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
            alsid INTEGER,
            email TEXT,
            lbnl_id TEXT,
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
            raw_json TEXT NOT NULL,
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


def format_report_table(rows: list[dict[str, str]]) -> str:
    headers = ["Beamline", "ESAFs", "New ESAFs", "Users", "New Users", "Error"]
    keys = ["beamline", "esafs", "new_esafs", "users", "new_users", "error"]
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


def print_report(rows: list[dict[str, str]], elapsed_seconds: float) -> None:
    if not rows:
        return

    typer.echo("\nBeamline sync report:")
    typer.echo(format_report_table(rows))
    typer.echo(f"Total time: {elapsed_seconds:.2f} seconds")


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
        INSERT INTO user (user_key, alsid, email, lbnl_id, name, orcid)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_key) DO UPDATE SET
            alsid = excluded.alsid,
            email = excluded.email,
            lbnl_id = excluded.lbnl_id,
            name = excluded.name,
            orcid = excluded.orcid
        """,
        (
            key,
            normalize_int(person.get("Alsid")),
            normalize_email(person.get("Email")),
            normalize_lbnl_id(person.get("LbnlId")),
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
            raw_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            raw_json = excluded.raw_json,
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
            json.dumps(esaf, sort_keys=True),
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
        Path("esafs.sqlite3"),
        "--db-path",
        help="SQLite database path. Defaults to ./esafs.sqlite3.",
    ),
    api_url: str = typer.Option(
        DEFAULT_API_URL,
        "--api-url",
        help="ESAF API base URL.",
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
            timeout=timeout,
        )
    )


def main() -> None:
    app()
