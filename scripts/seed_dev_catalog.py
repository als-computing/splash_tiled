from __future__ import annotations

import argparse
import os
import sqlite3
import time
from dataclasses import dataclass

import httpx
import numpy as np
from tiled.client import from_context
from tiled.client.context import Context, password_grant


@dataclass(frozen=True)
class EsafSeed:
    beamline: str
    esaf_id: str


SEED_PLAN = [
    EsafSeed(beamline="12.3.2", esaf_id="SB-01482-001"),
    EsafSeed(beamline="9.3.2", esaf_id="SB-00001-001"),
    EsafSeed(beamline="7.0.2", esaf_id="SB-00002-001"),
]


def wait_for_server(uri: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(uri, timeout=5.0)
            if response.status_code < 500:
                return
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"Timed out waiting for tiled server at {uri}")


def ensure_container(parent, key: str, metadata: dict) -> object:
    if key in parent:
        return parent[key]

    if hasattr(parent, "create_container"):
        parent.create_container(key=key, metadata=metadata)
        return parent[key]

    if hasattr(parent, "new"):
        parent.new(
            key=key,
            structure_family="container",
            metadata=metadata,
        )
        return parent[key]

    raise RuntimeError(
        f"Cannot create container '{key}'; no supported API on {type(parent)!r}"
    )


def write_array(
    parent, key: str, data: np.ndarray, access_blob: dict, metadata: dict
) -> None:
    if key in parent:
        return

    access_tags = access_blob.get("tags") if isinstance(access_blob, dict) else None

    if hasattr(parent, "write_array"):
        try:
            parent.write_array(
                data,
                key=key,
                metadata=metadata,
                access_tags=access_tags,
            )
            return
        except TypeError:
            # Older clients may use access_blob instead of access_tags.
            try:
                parent.write_array(
                    data,
                    key=key,
                    metadata=metadata,
                    access_blob=access_blob,
                )
                return
            except TypeError:
                pass

    if hasattr(parent, "new"):
        try:
            parent.new(
                key=key,
                structure_family="array",
                data=data,
                metadata=metadata,
                access_blob=access_blob,
            )
            return
        except TypeError:
            pass

    raise RuntimeError(
        f"Cannot write array '{key}'; no supported API on {type(parent)!r}"
    )


def load_defined_tags(compiled_tags_db: str) -> set[str]:
    try:
        with sqlite3.connect(compiled_tags_db) as conn:
            rows = conn.execute("SELECT name FROM tags").fetchall()
            return {row[0] for row in rows}
    except Exception as exc:
        print(f"Warning: could not load tags from {compiled_tags_db}: {exc}")
        return set()


def maybe_write_array(
    parent,
    *,
    key: str,
    data: np.ndarray,
    metadata: dict,
    tags: list[str],
    defined_tags: set[str],
) -> None:
    missing = [tag for tag in tags if defined_tags and tag not in defined_tags]
    if missing:
        print(f"Skipping {key}: undefined access tags {missing}")
        return
    write_array(
        parent,
        key=key,
        data=data,
        metadata=metadata,
        access_blob={"tags": tags},
    )


def authenticated_client(uri: str, username: str, password: str):
    # Avoid accidental API-key auth from ambient environment.
    os.environ.pop("TILED_API_KEY", None)
    os.environ.setdefault("TILED_CACHE_DIR", "/tmp/tiled-cache")
    context, node_path_parts = Context.from_any_uri(uri)
    providers = context.server_info.authentication.providers
    internal_provider = next(
        (
            p
            for p in providers
            if p.provider == "example" and p.mode in {"internal", "password"}
        ),
        None,
    )
    if internal_provider is None:
        internal_provider = next(
            (p for p in providers if p.mode in {"internal", "password"}),
            None,
        )
    if internal_provider is None:
        raise RuntimeError(
            "No internal/password auth provider available for seeded login"
        )

    tokens = password_grant(
        context.http_client,
        internal_provider.links["auth_endpoint"],
        internal_provider.provider,
        username,
        password,
    )
    context.configure_auth(tokens, remember_me=False)
    # Skip interactive auth path in from_context; we already configured tokens.
    context.has_external_auth = True
    return from_context(context, node_path_parts=node_path_parts, remember_me=False)


def seed(uri: str, username: str, password: str, compiled_tags_db: str) -> None:
    client = authenticated_client(uri, username=username, password=password)
    defined_tags = load_defined_tags(compiled_tags_db)
    beamlines = ensure_container(
        client,
        "beamlines",
        metadata={"description": "Top-level beamline container for dev testing"},
    )

    for plan in SEED_PLAN:
        beamline_container = ensure_container(
            beamlines,
            plan.beamline,
            metadata={"beamline": plan.beamline},
        )
        esaf_container = ensure_container(
            beamline_container,
            plan.esaf_id,
            metadata={"beamline": plan.beamline, "esaf_id": plan.esaf_id},
        )

        data = np.arange(64, dtype="float32").reshape(8, 8)

        maybe_write_array(
            esaf_container,
            key="public_overview",
            data=data,
            metadata={"access_case": "public"},
            tags=["public"],
            defined_tags=defined_tags,
        )
        maybe_write_array(
            esaf_container,
            key="beamline_staff_only",
            data=data + 100.0,
            metadata={"access_case": "beamline_staff"},
            tags=[f"{plan.beamline}-staff"],
            defined_tags=defined_tags,
        )
        maybe_write_array(
            esaf_container,
            key="esaf_only",
            data=data + 200.0,
            metadata={"access_case": "esaf_group"},
            tags=[plan.esaf_id],
            defined_tags=defined_tags,
        )
        maybe_write_array(
            esaf_container,
            key="esaf_and_beamline_staff",
            data=data + 300.0,
            metadata={"access_case": "combined"},
            tags=[plan.esaf_id, f"{plan.beamline}-staff"],
            defined_tags=defined_tags,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a tiled server with beamline/esaf containers and test arrays."
    )
    parser.add_argument(
        "--uri",
        default="http://tiled:8000",
        help="Tiled server URI.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=90,
        help="How long to wait for tiled server before failing.",
    )
    parser.add_argument(
        "--username",
        default="alice",
        help="Username to authenticate as when seeding data.",
    )
    parser.add_argument(
        "--password-env",
        default="ALICE_PASSWORD",
        help="Name of env var that stores the password.",
    )
    parser.add_argument(
        "--compiled-tags-db",
        default=os.getenv("COMPILED_TAGS_DB", "/app/tags/compiled_tags.db"),
        help="Path to compiled tags sqlite DB used to validate access tags.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = os.getenv(args.password_env)
    if not password:
        raise RuntimeError(f"Missing required password env var: {args.password_env}")
    wait_for_server(args.uri, args.wait_seconds)
    seed(
        args.uri,
        username=args.username,
        password=password,
        compiled_tags_db=args.compiled_tags_db,
    )
    print("Seeded dev catalog with beamline/esaf access-tagged arrays.")


if __name__ == "__main__":
    main()
