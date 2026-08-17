# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

"""Run a py_binary main.py with the container base Python and Bazel runfiles layout.

rules_python's default bootstrap execs the hermetic interpreter under .runfiles.
When that interpreter is omitted from the OCI image, base /usr/local/bin/python3
must still see the same import paths: workspace root (_main) and each pip
.../site-packages tree under RUNFILES_DIR.
"""

from __future__ import annotations

import os
import runpy
import sys


def _prepend_runfiles_import_path(runfiles: str) -> None:
    sites: list[str] = []
    for dirpath, dirnames, _filenames in os.walk(runfiles):
        if os.path.basename(dirpath) == "site-packages":
            sites.append(dirpath)
            dirnames.clear()
    prefix = [os.path.join(runfiles, "_main")] + sites
    sys.path[:0] = prefix


def main() -> None:
    runfiles = os.environ.get("RUNFILES_DIR")
    if not runfiles or not os.path.isdir(runfiles):
        sys.stderr.write(
            "oci_runfiles_launcher: RUNFILES_DIR must be set to the *.runfiles directory\n",
        )
        sys.exit(1)

    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: oci_runfiles_launcher.py <path-to-main.py> [args...]\n",
        )
        sys.exit(2)

    main_py = sys.argv[1]
    sys.argv = sys.argv[1:]
    _prepend_runfiles_import_path(runfiles)
    runpy.run_path(main_py, run_name="__main__")


if __name__ == "__main__":
    main()
