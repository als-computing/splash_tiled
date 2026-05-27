from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from tiled.client import from_uri
from tiled.structures.core import StructureFamily

from splash_tiled.access_control.inspect import app as query_app
from splash_tiled.access_control.tiled_tags import (
    compile_tags,
    get_default_tag_definitions_path,
)
from splash_tiled.access_control.user_office import (
    ALL_BEAMLINES,
    DEFAULT_API_URL,
    DEFAULT_PROPOSALS_BY_BL_URL,
    run,
)

app = typer.Typer(
    no_args_is_help=True, help="ALS access control management.", add_completion=False
)
compile_app = typer.Typer(
    no_args_is_help=True,
    help="Build ESAF and compiled-tags databases.",
    add_completion=False,
)

app.add_typer(query_app, no_args_is_help=True, name="query")
app.add_typer(compile_app, no_args_is_help=True, name="compile")

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
_PROPOSALS_BY_BL_URL = typer.Option(
    DEFAULT_PROPOSALS_BY_BL_URL,
    "--proposals-by-bl-url",
    help="Proposals-by-beamline API base URL.",
)
_TIMEOUT = typer.Option(30.0, "--timeout", help="HTTP timeout in seconds.")


def _resolve_tag_defs(tag_definitions: Optional[Path]) -> Path:
    return tag_definitions or get_default_tag_definitions_path()


@compile_app.command("useroffice")
def compile_useroffice(
    esaf_db: Path = _ESAF_DB,
    api_url: str = _API_URL,
    proposals_by_bl_url: str = _PROPOSALS_BY_BL_URL,
    timeout: float = _TIMEOUT,
) -> None:
    """Fetch all beamlines and staff from the User Office APIs into the ESAF database."""
    raise typer.Exit(
        run(
            beamlines=ALL_BEAMLINES,
            db_path=esaf_db,
            api_url=api_url,
            proposals_by_bl_url=proposals_by_bl_url,
            timeout=timeout,
        )
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
    proposals_by_bl_url: str = _PROPOSALS_BY_BL_URL,
    timeout: float = _TIMEOUT,
) -> None:
    """Fetch from User Office APIs then compile tags."""
    exit_code = run(
        beamlines=ALL_BEAMLINES,
        db_path=esaf_db,
        api_url=api_url,
        proposals_by_bl_url=proposals_by_bl_url,
        timeout=timeout,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
    compile_tags(
        output_sqlite_path=compiled_db,
        esaf_db_path=esaf_db,
        tag_definitions_path=_resolve_tag_defs(tag_definitions),
        generated_tag_definitions_path=generated_yaml,
    )


def _tag_recursive(node, tags: list[str], errors: list[str]) -> int:
    current_tags = (node.access_blob or {}).get("tags", [])
    if set(current_tags) == set(tags):
        typer.echo(f"  {node.uri}  (already set, skipping)")
        count = 0
    else:
        typer.echo(f"  {node.uri}  →  {tags}")
        try:
            node.patch_metadata(
                access_blob_patch={"tags": tags},
                content_type="application/merge-patch+json",
            )
            count = 1
        except Exception as exc:
            errors.append(f"  {node.uri}: {exc}")
            typer.echo(f"    ERROR: {exc}", err=True)
            count = 0
    if node.structure_family == StructureFamily.container:
        for key in node:
            count += _tag_recursive(node[key], tags, errors)
    return count


@app.command("set-access-tags", no_args_is_help=True)
def tag_path_command(
    path: Annotated[
        str, typer.Argument(help="Path within tiled (e.g. beamlines/12.3.2).")
    ],
    tags: Annotated[
        list[str],
        typer.Argument(
            help="Access tags to apply (space-separated, e.g. SB-01234-001 12.3.2-staff)."
        ),
    ],
    uri: str = typer.Option(
        "http://localhost:8000", "--uri", help="Tiled server base URI."
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", envvar="TILED_API_KEY", help="Tiled API key."
    ),
) -> None:
    """Recursively apply access tags to a tiled node and all its descendants.

    Example: access set-access-tags beamlines/12.3.2 SB-01234-001 12.3.2-staff --uri http://tiled:8000
    """
    client = from_uri(uri, api_key=api_key)
    node = client
    for part in (p for p in path.split("/") if p):
        node = node[part]
    errors: list[str] = []
    count = _tag_recursive(node, tags, errors)
    typer.echo(f"Tagged {count} nodes.")
    if errors:
        typer.echo(f"Skipped {len(errors)} nodes with errors:", err=True)
        for msg in errors:
            typer.echo(msg, err=True)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
