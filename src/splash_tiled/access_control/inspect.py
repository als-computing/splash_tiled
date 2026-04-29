from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    help="Query the ESAF database.",
    add_completion=False,
)

_DB_OPTION = typer.Option(
    Path("tags/esafs.db"),
    "--db-path",
    help="Path to the ESAF SQLite database.",
)

_COMPILED_DB_OPTION = typer.Option(
    Path("tags/compiled_tags.db"),
    "--compiled-db",
    help="Path to the compiled tags SQLite database.",
)


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        typer.echo(f"Database not found: {db_path}", err=True)
        raise typer.Exit(1)
    return sqlite3.connect(db_path)


@app.command("user-proposals")
def user_proposals(
    orcid: Annotated[str, typer.Argument(help="User ORCID.")],
    db_path: Path = _DB_OPTION,
) -> None:
    """List proposal groups a user belongs to."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.esaf_friendly_id, e.beamline_name, eu.role
            FROM esaf_user eu
            JOIN user u ON u.user_key = eu.user_key
            JOIN esaf e ON e.esaf_id = eu.esaf_id
            WHERE u.orcid = ?
            ORDER BY e.beamline_name, e.esaf_friendly_id, eu.role
            """,
            (orcid,),
        ).fetchall()
    if not rows:
        typer.echo(f"No proposals found for {orcid}")
        return
    typer.echo(f"{'ESAF':<20} {'BEAMLINE':<12} ROLE")
    typer.echo("-" * 45)
    for esaf_id, beamline, role in rows:
        typer.echo(f"{esaf_id:<20} {beamline:<12} {role}")


@app.command("user-beamlines")
def user_beamlines(
    orcid: Annotated[str, typer.Argument(help="User ORCID.")],
    db_path: Path = _DB_OPTION,
) -> None:
    """List beamline staff groups a user belongs to."""
    with _connect(db_path) as conn:
        name_row = conn.execute(
            "SELECT name FROM user WHERE orcid = ?", (orcid,)
        ).fetchone()
        rows = conn.execute(
            "SELECT beamline_name FROM beamline_staff_user WHERE user_name = ? ORDER BY beamline_name",
            (orcid,),
        ).fetchall()
    if not rows:
        typer.echo(f"No beamline staff groups found for {orcid}")
        return
    label = name_row[0] if name_row and name_row[0] else orcid
    typer.echo(f"{label} ({orcid})")
    typer.echo("-" * 40)
    for (beamline,) in rows:
        typer.echo(beamline)


def _esaf_where(
    beamline: Optional[str], proposal: Optional[str]
) -> tuple[str, list[str], str]:
    clauses = ["esaf_friendly_id IS NOT NULL"]
    params: list[str] = []
    if beamline:
        clauses.append("beamline_name = ?")
        params.append(beamline)
    if proposal:
        clauses.append("esaf_friendly_id LIKE ?")
        params.append(f"%{proposal}%")
    order = "esaf_friendly_id" if beamline else "beamline_name, esaf_friendly_id"
    return " AND ".join(clauses), params, order


@app.command("proposals")
def proposals(
    beamline: Optional[str] = typer.Option(
        None, "--beamline", help="Filter by exact beamline name."
    ),
    proposal: Optional[str] = typer.Option(
        None, "--proposal", help="Filter by proposal ID substring (case-insensitive)."
    ),
    db_path: Path = _DB_OPTION,
) -> None:
    """List distinct proposals, with optional filters."""
    where, params, order = _esaf_where(beamline, proposal)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT esaf_friendly_id, beamline_name, status FROM esaf WHERE {where} ORDER BY {order}",
            params,
        ).fetchall()
    if not rows:
        typer.echo("No proposals found.")
        return
    typer.echo(f"{'ESAF':<20} {'BEAMLINE':<12} STATUS")
    typer.echo("-" * 45)
    for esaf_id, bl, status in rows:
        typer.echo(f"{esaf_id:<20} {bl:<12} {status or ''}")


@app.command("esaf")
def esaf(
    beamline: Optional[str] = typer.Option(
        None, "--beamline", help="Filter by exact beamline name."
    ),
    proposal: Optional[str] = typer.Option(
        None, "--proposal", help="Filter by proposal ID substring (case-insensitive)."
    ),
    db_path: Path = _DB_OPTION,
) -> None:
    """List ESAFs with title, with optional filters."""
    where, params, order = _esaf_where(beamline, proposal)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT esaf_friendly_id, beamline_name, status, title FROM esaf WHERE {where} ORDER BY {order}",
            params,
        ).fetchall()
    if not rows:
        typer.echo("No ESAFs found.")
        return
    typer.echo(f"{'ESAF':<20} {'BEAMLINE':<12} {'STATUS':<12} TITLE")
    typer.echo("-" * 80)
    for esaf_id, bl, status, title in rows:
        title_col = (title or "")[:36]
        typer.echo(f"{esaf_id:<20} {bl:<12} {(status or ''):<12} {title_col}")


@app.command("beamlines")
def beamlines(
    db_path: Path = _DB_OPTION,
) -> None:
    """List distinct beamline groups."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name, esaf_count FROM beamline ORDER BY name"
        ).fetchall()
    if not rows:
        typer.echo("No beamlines found.")
        return
    typer.echo(f"{'BEAMLINE':<16} ESAFS")
    typer.echo("-" * 24)
    for name, count in rows:
        typer.echo(f"{name:<16} {count}")


@app.command("proposal-members")
def proposal_members(
    esaf_friendly_id: Annotated[
        str, typer.Argument(help="ESAF friendly ID (e.g. ALS-13362-001).")
    ],
    db_path: Path = _DB_OPTION,
) -> None:
    """List members of a proposal group."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT u.orcid, u.name, eu.role
            FROM esaf_user eu
            JOIN user u ON u.user_key = eu.user_key
            JOIN esaf e ON e.esaf_id = eu.esaf_id
            WHERE e.esaf_friendly_id = ?
            ORDER BY eu.role, u.orcid
            """,
            (esaf_friendly_id,),
        ).fetchall()
    if not rows:
        typer.echo(f"No members found for {esaf_friendly_id}")
        return
    typer.echo(f"{'ORCID':<22} {'NAME':<28} ROLE")
    typer.echo("-" * 60)
    for orcid, name, role in rows:
        typer.echo(f"{orcid or '':<22} {(name or ''):<28} {role}")


@app.command("beamline-members")
def beamline_members(
    beamline: Annotated[str, typer.Argument(help="Beamline name (e.g. 12.3.2).")],
    db_path: Path = _DB_OPTION,
) -> None:
    """List staff members of a beamline group."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT bsu.user_name, u.name
            FROM beamline_staff_user bsu
            LEFT JOIN user u ON u.orcid = bsu.user_name
            WHERE bsu.beamline_name = ?
            ORDER BY u.name, bsu.user_name
            """,
            (beamline,),
        ).fetchall()
    if not rows:
        typer.echo(f"No staff found for beamline {beamline}")
        return
    typer.echo(f"{'ORCID':<22} NAME")
    typer.echo("-" * 50)
    for orcid, name in rows:
        typer.echo(f"{orcid:<22} {name or ''}")


@app.command("tags")
def tags(
    orcid: Annotated[str, typer.Argument(help="User ORCID.")],
    compiled_db: Path = _COMPILED_DB_OPTION,
) -> None:
    """List all tags a user has access to, with their scopes."""
    with _connect(compiled_db) as conn:
        rows = conn.execute(
            """
            SELECT t.name,
                   t.is_public,
                   GROUP_CONCAT(s.name, ', ') AS scopes,
                   EXISTS (
                       SELECT 1 FROM tag_owners towner
                       WHERE towner.tag_id = t.id AND towner.user_id = u.id
                   ) AS is_owner
            FROM tags t
            JOIN tags_users_scopes tus ON tus.tag_id = t.id
            JOIN users u ON u.id = tus.user_id
            JOIN scopes s ON s.id = tus.scope_id
            WHERE u.name = ?
            GROUP BY t.name
            ORDER BY t.name
            """,
            (orcid,),
        ).fetchall()
    if not rows:
        typer.echo(f"No tags found for {orcid}")
        return
    typer.echo(f"{'TAG':<40} {'PUBLIC':<8} {'OWNER':<8} SCOPES")
    typer.echo("-" * 90)
    for tag, is_public, scopes, is_owner in rows:
        typer.echo(
            f"{tag:<40} {'yes' if is_public else 'no':<8} {'yes' if is_owner else 'no':<8} {scopes or ''}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
