#!/usr/bin/env python3
# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Replace the `map:` block in app/config/defaults.yaml.

Inputs are passed as flags; the script renders a canonical `map:` block and
splices it in place of the existing one. Stdlib-only.

Bundled map (resolves the image and its sibling Nav2 yaml for you):
  --map <name>

Any other source (exactly one), with the map's own Nav2 yaml:
  --source-type file --source /tmp/config/maps/<file>.png  --metadata-yaml /tmp/config/maps/<file>.yaml
  --source-type uri  --source https://...                  --metadata-yaml https://...
  --source-type s3   --source s3://bucket/key              --metadata-yaml s3://bucket/key.yaml

Metadata always comes from a Nav2 yaml. resolution and origin describe how the
map was captured and cannot be derived from the image, so there is no flag to
supply them by hand.

Flags:
  --push-on-startup            (sets push_map_on_startup: True; default False)
  --save-route-visualization   (sets save_route_visualization: True; default False)
  --dry-run                    (print, do not write)
  --list-bundled               (list bundled maps under app/config/maps/ and exit)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MC_WORKSPACE") or "skills-workspace").resolve()
_RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def _resolve_source(path: Path) -> Path:
    """Return `path` if it exists; else the same relative path under the
    shipped resources/. Never copies. Callers use the returned path only for
    reading."""
    if path.exists():
        return path
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return path
    fallback = _RESOURCES / rel
    return fallback if fallback.exists() else path
DEFAULTS_YAML = REPO_ROOT / "app" / "config" / "defaults.yaml"
MAPS_DIR = REPO_ROOT / "app" / "config" / "maps"
UPLOADED_MAPS_DIR = REPO_ROOT / "app" / "config" / "uploaded_maps"

CONTAINER_CONFIG_DIR = "/tmp/config"  # nosec B108


def _map_search_dirs() -> list[Path]:
    """Workspace first, then shipped — the order --source would resolve in."""
    rel = MAPS_DIR.relative_to(REPO_ROOT)
    return [MAPS_DIR, _RESOURCES / rel]


def seed_maps() -> list[str]:
    """Copy shipped map files the workspace does not have into it."""
    src_dir = _RESOURCES / MAPS_DIR.relative_to(REPO_ROOT)
    if not src_dir.is_dir():
        return []
    copied = []
    for entry in sorted(src_dir.iterdir()):
        if not entry.is_file():
            continue
        dst = MAPS_DIR / entry.name
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, dst)
        copied.append(entry.name)
    return copied


def resolve_map(name: str) -> Path:
    """Find a bundled map image by name. Raises LookupError if it cannot."""
    candidates: dict[str, Path] = {}
    for d in _map_search_dirs():
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if entry.is_file() and entry.suffix.lower() != ".yaml":
                candidates.setdefault(entry.name, entry)
    if not candidates:
        raise LookupError("no map files found in the workspace or the shipped resources")

    wanted = name.strip()
    for key in (wanted, f"{wanted}.png"):
        if key in candidates:
            return candidates[key]

    lowered = wanted.lower()
    partial = [n for n in candidates if lowered in Path(n).stem.lower()]
    if len(partial) == 1:
        return candidates[partial[0]]
    available = ", ".join(sorted(candidates))
    if partial:
        raise LookupError(f"{name!r} matches more than one map ({', '.join(sorted(partial))}); name one exactly")
    raise LookupError(f"no bundled map matches {name!r}; available: {available}")


def host_path_for_container(container_path: str) -> Path | None:
    """Map a /tmp/config/maps/... path back to the file on this host, if present."""
    prefix = f"{CONTAINER_CONFIG_DIR}/{MAPS_DIR.name}/"
    if not container_path.startswith(prefix):
        return None
    name = container_path[len(prefix):]
    for d in _map_search_dirs():
        candidate = d / name
        if candidate.is_file():
            return candidate
    return None


def resolve_sidecar(map_png: Path) -> Path | None:
    """Return the Nav2 yaml shipped beside a map image, if there is one."""
    for d in _map_search_dirs():
        candidate = d / f"{map_png.stem}.yaml"
        if candidate.is_file():
            return candidate
    return None


def read_sidecar_fields(path: Path) -> dict:
    """Pull `image:` and `origin:` out of a Nav2 yaml."""
    text = path.read_text()
    fields: dict = {}
    m = re.search(r"^\s*image:\s*(.+?)\s*$", text, re.M)
    if m:
        fields["image"] = m.group(1).strip().strip("\"'")
    m = re.search(r"^\s*origin:\s*\[([^\]]*)\]", text, re.M)
    if m:
        fields["origin"] = [part.strip() for part in m.group(1).split(",")]
    return fields



def replace_top_level_block(text: str, key: str, new_block: str) -> str:
    """Replace one top-level YAML block while preserving surrounding text."""
    lines = text.splitlines(keepends=True)
    start = None
    end = None
    key_re = re.compile(rf"^{re.escape(key)}:\s*$")
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if start is None:
            if key_re.match(stripped):
                start = i
            continue
        if stripped and not stripped.startswith((" ", "\t")) and not stripped.startswith("#"):
            end = i
            break
    if start is None:
        raise ValueError(f"top-level key {key!r} not found")
    if end is None:
        end = len(lines)
    if not new_block.endswith("\n"):
        new_block += "\n"
    return "".join(lines[:start]) + new_block + "".join(lines[end:])


RECOGNIZED_MAP_KEYS = (
    "map_file",
    "map_uri",
    "map_s3",
    "metadata_yaml",
    "metadata",
    "push_map_on_startup",
    "save_route_visualization",
)


def extract_trailing_commented(text: str) -> str | None:
    """Extract trailing commented/blank lines inside the existing `map:` block.

    Anything after the last recognized key line, before the next top-level key,
    is treated as preserved trailer (e.g. the `# docks:` hint block in
    defaults.yaml). Returns the trailer as a string (with trailing newline) or
    None if there is no trailer to preserve.
    """
    lines = text.splitlines(keepends=True)
    start = None
    end = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if start is None:
            if re.match(r"^map:\s*$", stripped):
                start = i
            continue
        if stripped and not stripped.startswith((" ", "\t")) and not stripped.startswith("#"):
            end = i
            break
    if start is None:
        return None
    if end is None:
        end = len(lines)
    block_lines = lines[start + 1 : end]

    key_re = re.compile(
        r"^  (?:" + "|".join(re.escape(k) for k in RECOGNIZED_MAP_KEYS) + r")\b"
    )
    last_recognized = -1
    in_metadata = False
    for i, line in enumerate(block_lines):
        stripped = line.rstrip("\n")
        if key_re.match(stripped):
            last_recognized = i
            in_metadata = stripped.startswith("  metadata:")
            continue
        if in_metadata and re.match(r"^    \S", stripped):
            last_recognized = i
            continue
        in_metadata = False
    trailer = block_lines[last_recognized + 1 :]
    while trailer and trailer[0].strip() == "":
        trailer.pop(0)
    while trailer and trailer[-1].strip() == "":
        trailer.pop()
    if not trailer:
        return None
    return "".join(trailer).rstrip("\n") + "\n"



def render_map_block(
    source_type: str,
    source: str,
    metadata_yaml: str,
    push_on_startup: bool,
    save_route_visualization: bool,
    trailer: str | None = None,
) -> str:
    """Render the canonical Mission Control map: config block."""
    lines = ["map:"]
    lines.append("  # One and only one of map_file, map_uri, or map_s3 must be set")
    lines.append(f'  map_file: "{source}"' if source_type == "file" else '  # map_file: ""')
    lines.append(f'  map_uri: "{source}"' if source_type == "uri" else '  # map_uri: ""')
    lines.append(f'  map_s3: "{source}"' if source_type == "s3" else "  # map_s3:")
    lines.append("")
    lines.append(f'  metadata_yaml: "{metadata_yaml}"')
    lines.append(f"  push_map_on_startup: {'True' if push_on_startup else 'False'}")
    lines.append(f"  save_route_visualization: {'True' if save_route_visualization else 'False'}")
    if trailer:
        lines.append("")
        for ln in trailer.splitlines():
            lines.append(ln)
    return "\n".join(lines) + "\n"


def list_bundled() -> int:
    """Print bundled and uploaded map files available to this skill.

    Reads the workspace and the shipped resources/ under the same two-tier
    convention the rest of the skill uses. Listing only the workspace would
    print nothing on a fresh install, where every map lives in resources/.
    Names are merged so a workspace copy shadows the shipped one, matching
    what --source would actually resolve to."""
    for d in (MAPS_DIR, UPLOADED_MAPS_DIR):
        rel = d.relative_to(REPO_ROOT)
        names: dict[str, str] = {}
        for tier, root in (("shipped", _RESOURCES / rel), ("workspace", d)):
            if root.is_dir():
                for entry in sorted(root.iterdir()):
                    if entry.is_file():
                        names[entry.name] = tier
        if not names:
            continue
        print(f"# {rel}")
        for name in sorted(names):
            print(f"{name}  ({names[name]})")
    return 0


def main() -> int:
    """Parse CLI arguments and apply the requested map config update."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", help="Name of a bundled map, e.g. 'nvidia_galileo'. Resolves the image and its Nav2 yaml for you.")
    ap.add_argument("--source-type", choices=["file", "uri", "s3"])
    ap.add_argument("--source", help="Path (container-side for 'file'), URL for 'uri', or s3:// for 's3'.")
    ap.add_argument("--metadata-yaml", help="Path or URI of the map's Nav2 yaml (sets the metadata_yaml: field). Optional with --map, which finds the sibling yaml itself.")
    ap.add_argument("--push-on-startup", action="store_true")
    ap.add_argument("--save-route-visualization", action="store_true")
    ap.add_argument("--defaults-yaml", default=str(DEFAULTS_YAML))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-bundled", action="store_true", help="List bundled and uploaded map files and exit.")
    args = ap.parse_args()

    if args.list_bundled:
        return list_bundled()

    if args.map and (args.source_type or args.source):
        ap.error("--map resolves the image itself; do not combine it with --source-type/--source.")
    if not args.map and not (args.source_type and args.source):
        ap.error("give --map NAME, or --source-type with --source (unless --list-bundled).")

    source_type = args.source_type
    source = args.source
    metadata_yaml = args.metadata_yaml

    if args.map:
        try:
            map_png = resolve_map(args.map)
        except LookupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 7
        source_type = "file"
        source = f"{CONTAINER_CONFIG_DIR}/{MAPS_DIR.name}/{map_png.name}"

        sidecar = resolve_sidecar(map_png)
        uses_sidecar = not args.metadata_yaml

        if sidecar is not None and uses_sidecar:
            fields = read_sidecar_fields(sidecar)
            declared = fields.get("image")
            if declared and Path(declared).name not in (map_png.name, map_png.stem):
                print(
                    f"error: {sidecar.name} declares image: {declared!r}, which is neither "
                    f"{map_png.name!r} nor {map_png.stem!r}. Mission Control uses that field as map_id "
                    "and as the WPG cache key, so a mismatch serves the wrong route graph.",
                    file=sys.stderr,
                )
                return 8
            origin = fields.get("origin") or []
            if len(origin) > 2:
                try:
                    yaw = float(origin[2])
                except ValueError:
                    yaw = 0.0
                if yaw != 0.0:
                    print(
                        f"warning: {sidecar.name} has a non-zero origin yaw ({origin[2]}); Mission Control "
                        "drops it. Pre-rotate the image instead if the orientation matters.",
                        file=sys.stderr,
                    )

        if args.metadata_yaml:
            supplied = host_path_for_container(args.metadata_yaml)
            declared = read_sidecar_fields(supplied).get("image") if supplied else None
            if declared is not None:
                mismatch = Path(declared).name not in (map_png.name, map_png.stem)
            else:
                mismatch = Path(args.metadata_yaml).stem != map_png.stem
            if mismatch:
                print(
                    f"error: --metadata-yaml {args.metadata_yaml!r} does not describe {map_png.name}. "
                    "Its resolution and origin belong to a different map, and Mission Control would "
                    "apply them to this image. Pass this map's own yaml, or omit the flag to use it.",
                    file=sys.stderr,
                )
                return 10

        if uses_sidecar:
            if sidecar is None:
                print(
                    f"error: no Nav2 yaml shipped beside {map_png.name}. Pass the map's own yaml with "
                    "--metadata-yaml. Its resolution and origin come from how the map was captured and "
                    "cannot be derived from the image, so do not substitute another map's values.",
                    file=sys.stderr,
                )
                return 9
            metadata_yaml = f"{CONTAINER_CONFIG_DIR}/{MAPS_DIR.name}/{sidecar.name}"
    elif not args.metadata_yaml:
        ap.error("--metadata-yaml is required (the map's Nav2 yaml), unless --map resolves it for you.")


    if source_type == "file" and not source.startswith("/"):
        print(
            f"warning: source {source!r} is not an absolute path. Mission Control reads map_file inside the container; the bind-mount puts app/config/ at /tmp/config/, so paths should look like /tmp/config/maps/<file>.png",
            file=sys.stderr,
        )
    if source_type == "s3" and not source.startswith("s3://"):
        print(f"warning: --source-type s3 expects an s3://... URL; got {source!r}", file=sys.stderr)
    if source_type == "uri" and not re.match(r"^https?://", source):
        print(f"warning: --source-type uri expects http(s)://...; got {source!r}", file=sys.stderr)

    d_path = Path(args.defaults_yaml)
    read_from = _resolve_source(d_path)
    if not read_from.is_file():
        print(f"error: defaults.yaml not found at {d_path}", file=sys.stderr)
        return 4

    old = read_from.read_text()



    trailer = extract_trailing_commented(old)
    new_block = render_map_block(
        source_type=source_type,
        source=source,
        metadata_yaml=metadata_yaml,
        push_on_startup=args.push_on_startup,
        save_route_visualization=args.save_route_visualization,
        trailer=trailer,
    )

    try:
        new = replace_top_level_block(old, "map", new_block)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 6

    print(f"--- {d_path} (new map: block) ---")
    print(new_block.rstrip())

    if args.dry_run:
        return 0
    seeded = seed_maps()
    if seeded:
        print(f"seeded {MAPS_DIR}: {', '.join(seeded)}")

    if new != old:
        d_path.parent.mkdir(parents=True, exist_ok=True)
        d_path.write_text(new)
        print(f"wrote {d_path}")
        print(
            "\nMission Control reads this file at startup, so the map has not changed yet. "
            "To start the stack with it, install the bring-up-cloud-stack skill from the "
            "mission-control repository and run its scripts/up.sh --recreate."
        )
    else:
        print(f"no-op for {d_path}")
        print(
            "\nThis map was already configured. If the stack has not been restarted since "
            "it was set, it is still serving the previous map: run bring-up-cloud-stack's "
            "scripts/up.sh --recreate."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
