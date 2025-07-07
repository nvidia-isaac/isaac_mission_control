# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import os
import subprocess
import sys


def shadowed_module(path: str) -> bool:
    """ Whether a path indicates a module that shadows a dist-package and should be excluded from
    mypy """
    shadowed_modules = [
        "typing_extensions", "mypy_extensions"
    ]
    return any(module in path for module in shadowed_modules)


def main():
    # Determine the module include paths that should be used by mypy
    paths = os.environ["PYTHONPATH"]
    fixed_paths = ":".join(path for path in paths.split(
        ":") if not shadowed_module(path))
    env = {
        "PYTHONPATH": paths,
        "MYPYPATH": fixed_paths
    }

    # Run mypy in a subprocess
    result = subprocess.run([sys.executable, "-m", "mypy",
                             "--explicit-package-bases", "--namespace-packages",
                             "--follow-imports", "silent", "--check-untyped-defs"] + sys.argv[1:],
                            env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
