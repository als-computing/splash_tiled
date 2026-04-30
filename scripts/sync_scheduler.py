from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

app = typer.Typer(add_completion=False)


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def get_env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def resolve_path_option(
    option_value: Path | None,
    env_name: str,
    default: str,
) -> Path:
    if option_value is not None:
        return option_value
    return Path(get_env(env_name, default))


def resolve_cron_expression(cron: str) -> str:
    if not cron:
        raise typer.BadParameter("SYNC_CRON environment variable is required.")
    return cron


def parse_beamline_args(beamlines: str) -> list[str]:
    if beamlines == "all":
        return ["--all"]

    selected = [value.strip() for value in beamlines.split(",")]
    selected = [value for value in selected if value]
    if not selected:
        raise ValueError("No valid BEAMLINES configured. Use a CSV list or 'all'.")

    args: list[str] = []
    for beamline in selected:
        args.extend(["--beamline", beamline])
    return args


def sync_once(
    esaf_db_path: Path,
    tags_template: Path,
    generated_tags_yaml: Path,
    compiled_tags_db: Path,
    api_url: str,
    beamlines: str,
) -> None:

    esaf_db_path.parent.mkdir(parents=True, exist_ok=True)
    generated_tags_yaml.parent.mkdir(parents=True, exist_ok=True)
    compiled_tags_db.parent.mkdir(parents=True, exist_ok=True)

    beamline_args = parse_beamline_args(beamlines)

    start = time.monotonic()
    typer.echo(f"[{utc_now()}] Sync started")

    t0 = time.monotonic()
    subprocess.run(
        [
            "python",
            "-m",
            "splash_tiled.access_control.user_office",
            *beamline_args,
            "--db-path",
            str(esaf_db_path),
            "--api-url",
            api_url,
        ],
        check=True,
    )
    typer.echo(
        f"[{utc_now()}] User Office fetch complete ({time.monotonic() - t0:.1f}s)"
    )

    t0 = time.monotonic()
    subprocess.run(
        [
            "python",
            "-m",
            "splash_tiled.access_control.tiled_tags",
            "compile",
            "--esaf-sqlite-path",
            str(esaf_db_path),
            "--output-sqlite-path",
            str(compiled_tags_db),
            "--tag-definitions-path",
            str(tags_template),
            "--generated-yaml-path",
            str(generated_tags_yaml),
        ],
        check=True,
    )
    typer.echo(f"[{utc_now()}] Tag compile complete ({time.monotonic() - t0:.1f}s)")
    typer.echo(f"[{utc_now()}] Sync finished — total {time.monotonic() - start:.1f}s")


@app.command()
def main(
    esaf_db_path: Path | None = typer.Option(
        None,
        "--esaf-db-path",
        help=(
            "Path to ESAF SQLite DB. If omitted, uses ESAF_DB_PATH "
            "(default: /app/tags/esafs.db)."
        ),
    ),
    tags_template: Path | None = typer.Option(
        None,
        "--tags-template",
        help=(
            "Path to tag template YAML. If omitted, uses TAGS_TEMPLATE "
            "(default: /app/src/splash_tiled/access_control/"
            "tag_definitions.yml)."
        ),
    ),
    generated_tags_yaml: Path | None = typer.Option(
        None,
        "--generated-tags-yaml",
        help=(
            "Path to generated tags YAML. If omitted, uses "
            "GENERATED_TAGS_YAML (default: /app/tags/"
            "tag_definitions.generated.yml)."
        ),
    ),
    compiled_tags_db: Path | None = typer.Option(
        None,
        "--compiled-tags-db",
        help=(
            "Path to compiled tags SQLite DB. If omitted, uses "
            "COMPILED_TAGS_DB (default: /app/tags/compiled_tags.db)."
        ),
    ),
) -> None:
    cron_expr = resolve_cron_expression(get_env("SYNC_CRON", ""))
    resolved_esaf_db_path = resolve_path_option(
        esaf_db_path,
        env_name="ESAF_DB_PATH",
        default="/app/tags/esafs.db",
    )
    resolved_tags_template = resolve_path_option(
        tags_template,
        env_name="TAGS_TEMPLATE",
        default="/app/src/splash_tiled/access_control/tag_definitions_stub.yaml",
    )
    resolved_generated_tags_yaml = resolve_path_option(
        generated_tags_yaml,
        env_name="GENERATED_TAGS_YAML",
        default="/app/tags/tag_definitions.generated.yml",
    )
    resolved_compiled_tags_db = resolve_path_option(
        compiled_tags_db,
        env_name="COMPILED_TAGS_DB",
        default="/app/tags/compiled_tags.db",
    )
    api_url = get_env(
        "API_URL",
        "https://als-esaf.als.lbl.gov/EsafInformation/GetEsaf",
    )
    beamlines = get_env("BEAMLINES", "all")

    scheduler = BlockingScheduler(timezone="UTC")

    # Prime the tags DB on service startup.
    sync_once(
        esaf_db_path=resolved_esaf_db_path,
        tags_template=resolved_tags_template,
        generated_tags_yaml=resolved_generated_tags_yaml,
        compiled_tags_db=resolved_compiled_tags_db,
        api_url=api_url,
        beamlines=beamlines,
    )

    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid --cron/SYNC_CRON expression: {cron_expr!r}"
        ) from exc

    scheduler.add_job(
        sync_once,
        trigger=trigger,
        id="esaf-sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        kwargs={
            "esaf_db_path": resolved_esaf_db_path,
            "tags_template": resolved_tags_template,
            "generated_tags_yaml": resolved_generated_tags_yaml,
            "compiled_tags_db": resolved_compiled_tags_db,
            "api_url": api_url,
            "beamlines": beamlines,
        },
    )
    typer.echo(f"[{utc_now()}] APScheduler started with cron: {cron_expr} (UTC)")

    scheduler.start()


if __name__ == "__main__":
    app()
