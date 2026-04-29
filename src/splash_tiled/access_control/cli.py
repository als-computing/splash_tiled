from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from splash_tiled.access_control.inspect import app as query_app
from splash_tiled.access_control.tiled_tags import (
    compile_tags,
    get_default_tag_definitions_path,
)
from splash_tiled.access_control.user_office import (
    ALL_BEAMLINES,
    DEFAULT_API_URL,
    run,
)

app = typer.Typer(help="ALS access control management.", add_completion=False)
compile_app = typer.Typer(
    help="Build ESAF and compiled-tags databases.", add_completion=False
)

app.add_typer(query_app, name="query")
app.add_typer(compile_app, name="compile")

_ESAF_DB = typer.Option(
    Path("tags/esafs.db"), "--esaf-db", help="ESAF SQLite database."
)
_COMPILED_DB = typer.Option(
    Path("tags/compiled_tags.db"),
    "--compiled-db",
    help="Compiled tags SQLite database.",
)
_GENERATED_YAML = typer.Option(
    Path("tags/tag_definitions.generated.yml"),
    "--generated-yaml",
    help="Generated tag definitions YAML.",
)
_TAG_DEFS = typer.Option(
    None,
    "--tag-definitions",
    help="Tag definitions stub YAML. Defaults to the package stub.",
)
_API_URL = typer.Option(DEFAULT_API_URL, "--api-url", help="ESAF API base URL.")
_TIMEOUT = typer.Option(30.0, "--timeout", help="HTTP timeout in seconds.")


def _resolve_tag_defs(tag_definitions: Optional[Path]) -> Path:
    return tag_definitions or get_default_tag_definitions_path()


@compile_app.command("useroffice")
def compile_useroffice(
    esaf_db: Path = _ESAF_DB,
    api_url: str = _API_URL,
    timeout: float = _TIMEOUT,
) -> None:
    """Fetch all beamlines and staff from the User Office APIs into the ESAF database."""
    raise typer.Exit(
        run(beamlines=ALL_BEAMLINES, db_path=esaf_db, api_url=api_url, timeout=timeout)
    )


@compile_app.command("compiled-tags")
def compile_compiled_tags(
    esaf_db: Path = _ESAF_DB,
    compiled_db: Path = _COMPILED_DB,
    generated_yaml: Path = _GENERATED_YAML,
    tag_definitions: Optional[Path] = _TAG_DEFS,
) -> None:
    """Generate the compiled-tags database from the ESAF database."""
    compile_tags(
        output_sqlite_path=compiled_db,
        esaf_db_path=esaf_db,
        tag_definitions_path=_resolve_tag_defs(tag_definitions),
        generated_tag_definitions_path=generated_yaml,
    )


@compile_app.command("all")
def compile_all(
    esaf_db: Path = _ESAF_DB,
    compiled_db: Path = _COMPILED_DB,
    generated_yaml: Path = _GENERATED_YAML,
    tag_definitions: Optional[Path] = _TAG_DEFS,
    api_url: str = _API_URL,
    timeout: float = _TIMEOUT,
) -> None:
    """Fetch from User Office APIs then compile tags."""
    exit_code = run(
        beamlines=ALL_BEAMLINES, db_path=esaf_db, api_url=api_url, timeout=timeout
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
    compile_tags(
        output_sqlite_path=compiled_db,
        esaf_db_path=esaf_db,
        tag_definitions_path=_resolve_tag_defs(tag_definitions),
        generated_tag_definitions_path=generated_yaml,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
