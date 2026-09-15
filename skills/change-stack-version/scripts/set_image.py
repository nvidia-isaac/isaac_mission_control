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

"""Set the image (full ref or just tag) for a Mission Control stack service.

Edits docker-compose/images.conf in place. Stdlib-only. Never reads or
writes the compose credentials file.

Examples:
  set_image.py --service mission-control --image nvcr.io/nvidia/isaac/mission-control:5.0.0
  set_image.py --service mission-dispatch --tag 4.6.0
  set_image.py --service cuopt --tag 25.10.0-cuda12.8-py3.12 --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Workspace root shared with the other mission-control skills via convention
# ($MC_WORKSPACE, default ./skills-workspace in the caller's cwd). Files
# under REPO_ROOT are treated as overrides: this script reads images.conf
# from REPO_ROOT if it exists there, otherwise falls back to the shipped
# copy in resources/. Writes always go to REPO_ROOT — the skill's shipped
# resources/ is never modified. That way the workspace stays empty until a
# real edit happens.
#
# This script only ever touches images.conf, never the compose credentials
# file. Image refs were split out precisely so that swapping a tag does not
# mean rewriting a file that also holds the broker and database secrets. Do
# not "helpfully" re-add a fallback to the credentials file here: bring-up
# sources that file first and images.conf second, so an image set here still
# wins over a stale duplicate left behind there.
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
DEFAULT_IMAGES_FILE = REPO_ROOT / "docker-compose" / "images.conf"

SERVICE_TO_VAR = {
    "mission-control": "MISSION_CONTROL_IMAGE",
    "mission-dispatch": "MISSION_DISPATCH_IMAGE",
    "mission-database": "MISSION_DATABASE_IMAGE",
    "mission-simulator": "MISSION_SIMULATOR_IMAGE",
    "mosquitto": "MOSQUITTO_IMAGE",
    "postgres": "POSTGRES_IMAGE",
    "wpg": "WPG_IMAGE",
    "swagger": "WPG_IMAGE",
    "cuopt": "CUOPT_IMAGE",
    "ota": "OTA_IMAGE",
    "esp": "ESP_IMAGE",
    "mas": "MAS_IMAGE",
}


def main() -> int:
    """Parse CLI arguments and update the requested compose image variable."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    ap.add_argument("--service", required=True, choices=sorted(set(SERVICE_TO_VAR)))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", help="Full image ref to set (everything after the '=').")
    g.add_argument("--tag", help="Keep the existing image repo, replace only the tag (substring after the final ':').")
    ap.add_argument(
        "--images-file",
        "--images-env",
        "--compose-config",
        "--env",
        dest="images_file",
        default=str(DEFAULT_IMAGES_FILE),
        help=f"Path to the compose image variable file (default: {DEFAULT_IMAGES_FILE})",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print the diff but do not write.")
    args = ap.parse_args()

    var = SERVICE_TO_VAR[args.service]
    env_path = Path(args.images_file)
    read_from = _resolve_source(env_path)
    if not read_from.is_file():
        print(f"error: compose image variable file not found at {env_path}", file=sys.stderr)
        return 2

    lines = read_from.read_text().splitlines(keepends=True)
    line_re = re.compile(rf"^{re.escape(var)}=(.*)$")

    new_lines: list[str] = []
    found = False
    old_value: str | None = None
    new_value: str | None = None
    for line in lines:
        m = line_re.match(line.rstrip("\n"))
        if m and not found:
            found = True
            old_value = m.group(1)
            if args.image is not None:
                new_value = args.image
            else:
                if ":" not in old_value:
                    print(f"error: existing value {old_value!r} has no ':' to swap a tag into; pass --image instead.", file=sys.stderr)
                    return 3
                head = old_value.rsplit(":", 1)[0]
                new_value = f"{head}:{args.tag}"
            new_lines.append(f"{var}={new_value}\n")
        else:
            new_lines.append(line)

    if not found:
        print(f"error: variable {var} not found in {read_from}", file=sys.stderr)
        return 4

    if old_value == new_value:
        print(f"no-op: {var} already set to {new_value}")
        return 0

    print(f"--- {var}={old_value}")
    print(f"+++ {var}={new_value}")
    if args.dry_run:
        return 0

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("".join(new_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
