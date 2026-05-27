import logging
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

import typer
import yaml  # type: ignore[import-untyped]
from tiled.access_control.access_tags import AccessTagsCompiler
from tiled.access_control.scopes import ALL_SCOPES

from splash_tiled.access_control.user_office import (
    get_beamline_staff_group_map,
    get_beamlines_by_proposal,
    get_esaf_friendly_ids_by_beamline,
    get_esaf_orcid_map,
    get_proposal_orcid_map,
)

logger = logging.getLogger(__name__)
app = typer.Typer(add_completion=False)


def get_default_esaf_db_path() -> Path:
    return Path(__file__).resolve().parents[3] / "esafs.db"


def get_default_output_sqlite_path() -> Path:
    return Path(__file__).resolve().parent / "compiled_tags.db"


def get_default_tag_definitions_path() -> Path:
    return Path(__file__).resolve().parent[3] / "tags" / "tag_definitions_stub.yaml"


def get_default_generated_tag_definitions_path() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "tags" / "tag_definitions.generated.yml"
    )


def load_esaf_groups(esaf_db_path: Path) -> dict[str, list[str]]:
    with sqlite3.connect(esaf_db_path) as connection:
        groups = get_esaf_orcid_map(connection)
        groups.update(get_proposal_orcid_map(connection))
        beamline_staff_groups = get_beamline_staff_group_map(connection)
        for beamline_name, staff_orcids in beamline_staff_groups.items():
            groups[f"{beamline_name}-staff"] = staff_orcids
        return groups


def load_tag_definitions_template(tag_definitions_path: Path) -> dict[str, Any]:
    with tag_definitions_path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    if not isinstance(loaded, dict):
        raise typer.BadParameter(
            f"Expected a mapping at the top level of {tag_definitions_path}.",
            param_hint="--tag-definitions-path",
        )

    return loaded


def build_generated_tag_definitions(
    esaf_db_path: Path,
    tag_definitions_path: Path,
) -> dict[str, Any]:
    template = load_tag_definitions_template(tag_definitions_path)
    with sqlite3.connect(esaf_db_path) as connection:
        esaf_ids_by_beamline = get_esaf_friendly_ids_by_beamline(connection)
        beamline_staff_groups = get_beamline_staff_group_map(connection)
        beamlines_by_proposal = get_beamlines_by_proposal(connection)

    esaf_friendly_id_set = {
        esaf_friendly_id
        for esaf_friendly_ids in esaf_ids_by_beamline.values()
        for esaf_friendly_id in esaf_friendly_ids
    }
    proposal_friendly_id_set = set(beamlines_by_proposal.keys())

    template_tags = template.get("tags") or {}
    if not isinstance(template_tags, dict):
        raise typer.BadParameter(
            f"Expected 'tags' to be a mapping in {tag_definitions_path}.",
            param_hint="--tag-definitions-path",
        )

    generated_tags = {
        name: value
        for name, value in template_tags.items()
        if name not in esaf_friendly_id_set
        and name not in proposal_friendly_id_set
        and not any(
            name in (f"{id_}-raw", f"{id_}-processed")
            for id_ in esaf_friendly_id_set | proposal_friendly_id_set
        )
    }

    all_beamlines_with_staff = set(esaf_ids_by_beamline) | set(beamline_staff_groups)
    for beamline_name in all_beamlines_with_staff:
        beamline_staff_group_name = f"{beamline_name}-staff"
        generated_tags.setdefault(
            beamline_staff_group_name,
            {
                "groups": [
                    {
                        "name": beamline_staff_group_name,
                        "role": "facility_user",
                    }
                ]
            },
        )

    for beamline_name, esaf_friendly_ids in esaf_ids_by_beamline.items():
        beamline_staff_group_name = f"{beamline_name}-staff"

        if beamline_name not in beamline_staff_groups:
            beamline_staff_groups[beamline_name] = []

        for esaf_friendly_id in esaf_friendly_ids:
            esaf_groups_read = [
                {"name": esaf_friendly_id, "role": "facility_user"},
                {"name": beamline_staff_group_name, "role": "facility_user"},
            ]
            esaf_groups_write = [
                {"name": esaf_friendly_id, "role": "data_contributor"},
                {"name": beamline_staff_group_name, "role": "data_contributor"},
            ]
            generated_tags[f"{esaf_friendly_id}-raw"] = {
                "groups": esaf_groups_read,
                "auto_tags": [{"name": beamline_staff_group_name}],
            }
            generated_tags[f"{esaf_friendly_id}-processed"] = {
                "groups": esaf_groups_write,
                "auto_tags": [
                    {"name": "data_admin"},
                    {"name": beamline_staff_group_name},
                ],
            }

    for proposal_friendly_id, beamline_names in beamlines_by_proposal.items():
        proposal_groups_read = [{"name": proposal_friendly_id, "role": "facility_user"}]
        proposal_groups_write = [
            {"name": proposal_friendly_id, "role": "data_contributor"}
        ]
        proposal_auto_tags_raw = []
        proposal_auto_tags_processed = [{"name": "data_admin"}]
        for beamline_name in beamline_names:
            beamline_staff_group_name = f"{beamline_name}-staff"
            proposal_groups_read.append(
                {"name": beamline_staff_group_name, "role": "facility_user"}
            )
            proposal_groups_write.append(
                {"name": beamline_staff_group_name, "role": "data_contributor"}
            )
            proposal_auto_tags_raw.append({"name": beamline_staff_group_name})
            proposal_auto_tags_processed.append({"name": beamline_staff_group_name})
        generated_tags[f"{proposal_friendly_id}-raw"] = {
            "groups": proposal_groups_read,
            "auto_tags": proposal_auto_tags_raw,
        }
        generated_tags[f"{proposal_friendly_id}-processed"] = {
            "groups": proposal_groups_write,
            "auto_tags": proposal_auto_tags_processed,
        }

    return {
        "roles": template.get("roles") or {},
        "tags": generated_tags,
        "tag_owners": template.get("tag_owners") or {},
    }


def write_tag_definitions_yaml(
    tag_definitions: dict[str, Any],
    output_yaml_path: Path,
) -> Path:
    resolved_output_yaml_path = output_yaml_path.expanduser().resolve()
    resolved_output_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    with resolved_output_yaml_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(tag_definitions, file, sort_keys=False)

    return resolved_output_yaml_path


def generate_tag_definitions_yaml(
    esaf_db_path: Path,
    tag_definitions_path: Path,
    output_yaml_path: Path,
) -> Path:
    generated_tag_definitions = build_generated_tag_definitions(
        esaf_db_path=esaf_db_path,
        tag_definitions_path=tag_definitions_path,
    )
    return write_tag_definitions_yaml(generated_tag_definitions, output_yaml_path)


def resolve_output_sqlite_path(output_sqlite_path: Path) -> Path:
    return output_sqlite_path.expanduser().resolve()


def ensure_output_sqlite_path(output_sqlite_path: Path) -> Path:
    resolved_output_sqlite_path = resolve_output_sqlite_path(output_sqlite_path)
    resolved_output_sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resolved_output_sqlite_path.touch(exist_ok=True)
    except OSError as exc:
        raise typer.BadParameter(
            (
                "Cannot create compiled tags database at "
                f"{resolved_output_sqlite_path}. Choose a writable path."
            ),
            param_hint="--output-sqlite-path",
        ) from exc

    return resolved_output_sqlite_path


def build_sqlite_uri(sqlite_path: Path) -> str:
    resolved_sqlite_path = resolve_output_sqlite_path(sqlite_path)
    return f"file:{quote(resolved_sqlite_path.as_posix(), safe='/')}"


def build_group_parser(esaf_db_path: Path):
    groups = load_esaf_groups(esaf_db_path)

    def group_parser(groupname):
        return groups.get(groupname, [])

    return group_parser


def compile_tags(
    output_sqlite_path: Path,
    esaf_db_path: Path,
    tag_definitions_path: Path,
    generated_tag_definitions_path: Path,
) -> None:
    resolved_output_sqlite_path = ensure_output_sqlite_path(output_sqlite_path)
    resolved_generated_tag_definitions_path = generate_tag_definitions_yaml(
        esaf_db_path=esaf_db_path,
        tag_definitions_path=tag_definitions_path,
        output_yaml_path=generated_tag_definitions_path,
    )

    logger.info(
        "Compiling tags from %s → %s",
        resolved_generated_tag_definitions_path,
        resolved_output_sqlite_path,
    )
    access_tags_compiler = AccessTagsCompiler(
        ALL_SCOPES,
        resolved_generated_tag_definitions_path,
        {"uri": build_sqlite_uri(resolved_output_sqlite_path)},
        build_group_parser(esaf_db_path),
    )

    access_tags_compiler.load_tag_config()
    access_tags_compiler.compile()
    access_tags_compiler.connection.close()


@app.command("generate-yaml")
def generate_yaml_command(
    output_yaml_path: Path = typer.Option(
        get_default_generated_tag_definitions_path(),
        "--output-yaml-path",
        help="Path for the generated tag definitions YAML file.",
    ),
    esaf_db_path: Path = typer.Option(
        get_default_esaf_db_path(),
        "--esaf-sqlite-path",
        help="Path to the ESAF SQLite database used to build ESAF tags.",
    ),
    tag_definitions_path: Path = typer.Option(
        get_default_tag_definitions_path(),
        "--tag-definitions-path",
        help="Path to the template tag definitions YAML file.",
    ),
) -> None:
    resolved_output_yaml_path = generate_tag_definitions_yaml(
        esaf_db_path=esaf_db_path,
        tag_definitions_path=tag_definitions_path,
        output_yaml_path=output_yaml_path,
    )
    typer.echo(f"Generated tag definitions at {resolved_output_yaml_path}")


@app.command("compile")
def compile_command(
    output_sqlite_path: Path = typer.Option(
        get_default_output_sqlite_path(),
        "--output-sqlite-path",
        help="Path for the compiled tags SQLite database.",
    ),
    esaf_db_path: Path = typer.Option(
        get_default_esaf_db_path(),
        "--esaf-sqlite-path",
        help="Path to the ESAF SQLite database used to resolve groups.",
    ),
    tag_definitions_path: Path = typer.Option(
        get_default_tag_definitions_path(),
        "--tag-definitions-path",
        help="Path to the template tag definitions YAML file.",
    ),
    generated_tag_definitions_path: Path = typer.Option(
        get_default_generated_tag_definitions_path(),
        "--generated-yaml-path",
        help=(
            "Path for the generated tag definitions YAML file passed to "
            "AccessTagsCompiler."
        ),
    ),
) -> None:
    compile_tags(
        output_sqlite_path=output_sqlite_path,
        esaf_db_path=esaf_db_path,
        tag_definitions_path=tag_definitions_path,
        generated_tag_definitions_path=generated_tag_definitions_path,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
