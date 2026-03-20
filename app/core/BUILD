# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@rules_python//python:defs.bzl", "py_library")
load("@python_third_party//:requirements.bzl", "requirement")

py_library(
    name = "core",
    srcs = [
        "mission_control.py",
        "mission_control_config.py",
        "robots.py",
        "task.py",
        "sap_ewm_background.py"
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//app/api",
        "//app/common",
        "//app/core/objectives",
        "//:cloud_common_objects",
        requirement("httpx"),
        requirement("numpy"),
        requirement("pydantic"),
        requirement("py_trees"),
        requirement("requests"),
        requirement("scipy"),
        requirement("pyyaml"),
        requirement("Pillow"),
    ],
)
