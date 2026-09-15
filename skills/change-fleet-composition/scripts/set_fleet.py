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

"""Set the Mission Control fleet, syncing two files.

The script updates:

  - app/config/defaults.yaml   (top-level `robots:` block)
  - docker-compose/bringup_services.yaml   (`robot-simulator` service `command:`)

The fleet is declared as a JSON list of robot objects. Required fields are
`name`, plus `x` and `y` when `sim` is true. Optional fields are `labels`,
`heartbeat_timeout`, and `sim`.

Examples:
  set_fleet.py --show
  set_fleet.py --fleet-file fleet.json --dry-run
  set_fleet.py --fleet-json '[...]'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

JSON_OUTPUT_INDENT = 2
EXIT_INVALID_FLEET = 2
EXIT_MISSING_DEFAULTS = 3
EXIT_DEFAULTS_EDIT = 4
EXIT_BRINGUP_EDIT = 5

# Workspace root shared with the other mission-control skills via convention
# ($MC_WORKSPACE, default ./skills-workspace in the caller's cwd). Files
# under REPO_ROOT are treated as overrides: this script reads from
# REPO_ROOT if the file is there, otherwise falls back to the shipped copy
# in resources/. Writes always go to REPO_ROOT — the skill's shipped
# resources/ is never modified. That way the workspace stays empty until a
# real edit happens.
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
BRINGUP_YAML = REPO_ROOT / "docker-compose" / "bringup_services.yaml"

DEFAULT_LABELS = ["test", "carter", "ros"]
DEFAULT_HEARTBEAT = 30


def render_robots_block(fleet: list[dict]) -> str:
    """Render a canonical robots: YAML block from a fleet declaration."""
    lines = ["robots:"]
    for r in fleet:
        name = r["name"]
        labels = r.get("labels", DEFAULT_LABELS)
        hb = r.get("heartbeat_timeout", DEFAULT_HEARTBEAT)
        labels_str = "[" + ", ".join(f'"{l}"' for l in labels) + "]"
        lines.append(f'  - name: "{name}"')
        lines.append(f"    labels: {labels_str}")
        lines.append(f"    heartbeat_timeout: {hb}")
    return "\n".join(lines) + "\n"


def replace_top_level_block(text: str, key: str, new_block: str) -> str:
    """Replace the lines from `key:` up to (but not including) the next top-level key."""
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


def parse_robots_block(text: str) -> list[dict]:
    """Best-effort parse of the existing robots: block, for --show."""
    lines = text.splitlines()
    inside = False
    out: list[dict] = []
    current: dict | None = None
    for line in lines:
        if not inside:
            if re.match(r"^robots:\s*$", line):
                inside = True
            continue
        if line and not line.startswith((" ", "\t")) and not line.startswith("#"):
            break
        m_name = re.match(r"\s*-\s*name:\s*\"?(?P<name>[^\"\n]+)\"?\s*$", line)
        if m_name:
            if current is not None:
                out.append(current)
            current = {"name": m_name.group("name")}
            continue
        m_labels = re.match(r"\s*labels:\s*(?P<labels>\[.*\])\s*$", line)
        if m_labels and current is not None:
            try:
                current["labels"] = json.loads(m_labels.group("labels").replace("'", '"'))
            except Exception:
                pass
            continue
        m_hb = re.match(r"\s*heartbeat_timeout:\s*(?P<heartbeat_timeout>\d+)\s*$", line)
        if m_hb and current is not None:
            current["heartbeat_timeout"] = int(m_hb.group("heartbeat_timeout"))
            continue
    if current is not None:
        out.append(current)
    return out


def update_bringup_command(text: str, sim_robots: list[dict]) -> str:
    """Rewrite the robot-simulator service command: line. No-op if the service is absent."""
    pattern = re.compile(
        r"(?P<prefix>^  robot-simulator:\n(?:    .*\n)*?)(?P<command>    command:\s*\[.*?\]\n)",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return text
    if not sim_robots:
        new_cmd_line = '    command: ["--robots", ""]\n'
    else:
        parts = []
        for r in sim_robots:
            if "x" not in r or "y" not in r:
                raise ValueError(f"sim robot {r['name']!r} is missing x/y spawn pose")
            parts.append(f'"{r["name"]},{r["x"]},{r["y"]}"')
        new_cmd_line = f'    command: ["--robots", {", ".join(parts)}]\n'
    return text[: m.start("command")] + new_cmd_line + text[m.end("command") :]


def parse_bringup_command(text: str) -> dict:
    """Return {name: (x, y)} for the robots the simulator is currently launched with."""
    pattern = re.compile(
        r"(?P<prefix>^  robot-simulator:\n(?:    .*\n)*?)    command:\s*\[(?P<args>.*?)\]\n",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return {}
    current = {}
    for token in re.findall(r'"([^"]*)"', m.group("args")):
        if token == "--robots" or not token:
            continue
        parts = token.split(",")
        if len(parts) == 3:
            current[parts[0]] = (parts[1], parts[2])
    return current


def apply_sim_defaults(fleet: list[dict], current: dict) -> None:
    """Fill in `sim` and the spawn pose for robots that did not state them.

    A robot the simulator already launches keeps doing so, at the pose it
    already has. A robot that is new to the simulator defaults to real
    hardware, which is what Mission Control runs when nobody starts the
    robot-simulator profile.
    """
    for r in fleet:
        if not isinstance(r, dict) or "name" not in r:
            continue
        known = current.get(str(r["name"]))
        if "sim" not in r:
            r["sim"] = bool(known) or ("x" in r and "y" in r)
        if r["sim"] and known:
            r.setdefault("x", known[0])
            r.setdefault("y", known[1])


def validate_fleet(fleet: list[dict]) -> None:
    """Validate fleet shape, names, and simulator spawn requirements."""
    if not isinstance(fleet, list) or not fleet:
        raise ValueError("fleet must be a non-empty JSON list")
    names = []
    for r in fleet:
        if not isinstance(r, dict) or "name" not in r:
            raise ValueError(f"each robot must be an object with a 'name': {r!r}")
        if not re.match(r"^[A-Za-z0-9_\-]+$", str(r["name"])):
            raise ValueError(f"robot name {r['name']!r} must be alphanumeric/underscore/dash only")
        names.append(r["name"])
        if r.get("sim", True):
            if "x" not in r or "y" not in r:
                raise ValueError(f"sim robot {r['name']!r} requires numeric x and y spawn pose")
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate robot names in fleet: {names}")


def main() -> int:
    """Parse CLI arguments and apply the requested fleet update."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--fleet-json", help="Fleet declaration as a JSON string.")
    g.add_argument("--fleet-file", help="Path to a JSON file with the fleet declaration.")
    g.add_argument("--show", action="store_true", help="Print the current parsed robots: block and exit.")
    ap.add_argument("--defaults-yaml", default=str(DEFAULTS_YAML))
    ap.add_argument("--bringup-yaml", default=str(BRINGUP_YAML))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    d_path = Path(args.defaults_yaml)
    b_path = Path(args.bringup_yaml)
    d_read = _resolve_source(d_path)
    b_read = _resolve_source(b_path)

    if args.show:
        if not d_read.is_file():
            print(f"error: defaults.yaml not found at {d_path}", file=sys.stderr)
            return EXIT_MISSING_DEFAULTS
        shown = parse_robots_block(d_read.read_text())
        current = parse_bringup_command(b_read.read_text()) if b_read.is_file() else {}
        for r in shown:
            known = current.get(str(r.get("name")))
            r["sim"] = bool(known)
            if known:
                r["x"], r["y"] = float(known[0]), float(known[1])
        print(json.dumps(shown, indent=JSON_OUTPUT_INDENT))
        return os.EX_OK

    if args.fleet_json:
        fleet = json.loads(args.fleet_json)
    elif args.fleet_file:
        fleet = json.loads(Path(args.fleet_file).read_text())
    else:
        ap.error("one of --fleet-json / --fleet-file / --show is required")

    current_sim = parse_bringup_command(b_read.read_text()) if b_read.is_file() else {}
    apply_sim_defaults(fleet, current_sim)

    try:
        validate_fleet(fleet)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INVALID_FLEET

    dropped = [n for n in current_sim if n not in {str(r["name"]) for r in fleet if r.get("sim")}]
    if dropped:
        print(
            f"note: {', '.join(dropped)} will no longer be started by the simulator.",
            file=sys.stderr,
        )

    if not d_read.is_file():
        print(f"error: defaults.yaml not found at {d_path}", file=sys.stderr)
        return EXIT_MISSING_DEFAULTS

    old_d = d_read.read_text()
    try:
        new_d = replace_top_level_block(old_d, "robots", render_robots_block(fleet))
    except ValueError as e:
        print(f"error editing {d_path}: {e}", file=sys.stderr)
        return EXIT_DEFAULTS_EDIT

    sim_robots = [r for r in fleet if r.get("sim", True)]
    if b_read.is_file():
        old_b = b_read.read_text()
        try:
            new_b = update_bringup_command(old_b, sim_robots)
        except ValueError as e:
            print(f"error editing {b_path}: {e}", file=sys.stderr)
            return EXIT_BRINGUP_EDIT
    else:
        old_b = new_b = ""

    print(f"--- {d_path} (new robots: block) ---")
    print(render_robots_block(fleet).rstrip())
    if b_read.is_file():
        print(f"--- {b_path} (new robot-simulator command) ---")
        if sim_robots:
            parts = ", ".join(f'"{r["name"]},{r["x"]},{r["y"]}"' for r in sim_robots)
            print(f'    command: ["--robots", {parts}]')
        else:
            print('    command: ["--robots", ""]   (no simulated robots; robot-simulator profile will spawn none)')

    if args.dry_run:
        return os.EX_OK

    changed = False
    if new_d != old_d:
        d_path.parent.mkdir(parents=True, exist_ok=True)
        d_path.write_text(new_d)
        print(f"wrote {d_path}")
        changed = True
    else:
        print(f"no-op for {d_path}")
    if b_read.is_file():
        if new_b != old_b:
            b_path.parent.mkdir(parents=True, exist_ok=True)
            b_path.write_text(new_b)
            print(f"wrote {b_path}")
            changed = True
        else:
            print(f"no-op for {b_path}")
    else:
        print(
            f"\nwarning: {b_path} not found, so the simulator was not synced. "
            f"{d_path.name} now advertises this fleet, but the robot-simulator "
            "service will keep spawning whichever robots its own command: line "
            "names. Run bring-up-cloud-stack's scripts/up.sh once to seed the "
            "workspace, then re-run this script.",
            file=sys.stderr,
        )

    if not b_read.is_file():
        return os.EX_OK

    restart = "scripts/up.sh --with-sim --recreate" if sim_robots else "scripts/up.sh --recreate"
    if changed:
        print(
            "\nMission Control reads these files at startup, so the fleet has not "
            "changed yet. To start the stack with it, install the bring-up-cloud-stack "
            f"skill from the mission-control repository and run its {restart}."
        )
    else:
        print(
            "\nThis fleet was already configured. If the stack has not been restarted "
            "since it was set, it is still running the previous fleet: run "
            f"bring-up-cloud-stack's {restart}."
        )
    return os.EX_OK


if __name__ == "__main__":
    raise SystemExit(main())
