# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@io_bazel_rules_docker//container:container.bzl", "container_image")

exports_files([
    "pylintrc",
    "pytype.py",
    "pylint.py",
])

container_image(
    name = "python_base",
    base = "@loaded_base_docker_image//image",
    visibility = ["//visibility:public"],
)
