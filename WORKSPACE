# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

workspace(name = "nvidia_isaac_mission_control")

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("//bzl:engine.bzl", "engine_workspace")

engine_workspace()

load("@pybind11_bazel//:python_configure.bzl", "python_configure")
python_configure(name = "local_config_python")

bind(
    name = "zlib",
    actual = "@net_zlib_zlib//:zlib",
)

# Include rules needed for pip
http_archive(
    name = "rules_python",
    sha256 = "94750828b18044533e98a129003b6a68001204038dc4749f40b195b24c38f49f",
    strip_prefix = "rules_python-0.21.0",
    url = "https://github.com/bazelbuild/rules_python/releases/download/0.21.0/rules_python-0.21.0.tar.gz",
)

load("@rules_python//python:repositories.bzl", "py_repositories")

py_repositories()

# Include rules
http_archive(
    name = "io_bazel_rules_docker",
    sha256 = "b1e80761a8a8243d03ebca8845e9cc1ba6c82ce7c5179ce2b295cd36f7e394bf",
    urls = ["https://github.com/bazelbuild/rules_docker/releases/download/v0.25.0/rules_docker-v0.25.0.tar.gz"],
)

load(
    "@io_bazel_rules_docker//repositories:repositories.bzl",
    container_repositories = "repositories",
)

container_repositories()

load("@rules_python//python:pip.bzl", "pip_parse")

pip_parse(
    name = "python_third_party",
    requirements_lock = "//bzl:requirements.txt",
)

pip_parse(
    name = "python_third_party_linting",
    requirements_lock = "//bzl:requirements_linting.txt",
)

# Setup workspace for mission control
load("//:deps.bzl", "mission_control_workspace")

mission_control_workspace()
