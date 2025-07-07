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


def main():
    # Run pylint in a subprocess
    result = subprocess.run([sys.executable, "-m", "pylint"] + sys.argv[1:],
                            env={"PYTHONPATH": os.environ["PYTHONPATH"]})
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
