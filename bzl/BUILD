# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@python_versions//3.10:defs.bzl", compile_pip_requirements = "compile_pip_requirements")

package(default_visibility = ["//visibility:public"])

compile_pip_requirements(
    name = "python_third_party",
    src = "requirements.txt",
    requirements_txt = "requirements_lock.txt",
)

compile_pip_requirements(
    name = "python_third_party_linting",
    src = "requirements_linting.txt",
    requirements_txt = "requirements_linting_lock.txt",
)

exports_files([
    "pylintrc",
    "pytype.py",
    "pylint.py",
])
