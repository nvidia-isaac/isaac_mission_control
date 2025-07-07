# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("//bzl:python.bzl", "mission_control_py_library")
load("@python_third_party//:requirements.bzl", "requirement")

mission_control_py_library(
    name = "common",
    srcs = [
        "metrics.py",
        "models.py",
        "telemetry_base.py",
        "utils.py",
        "waypoint_graph.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//:cloud_common_objects",
        requirement("pydantic"),
    ],
) 