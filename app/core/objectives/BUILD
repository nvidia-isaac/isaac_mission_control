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
    name = "objectives",
    srcs = [
        "objective_behavior_tree.py",
        "objectives.py",
        "objectives_context.py",
        "objectives_conditional.py",
        "objectives_common.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//:cloud_common_objects",
        requirement("pydantic"),
        requirement("py_trees"),
    ],
)
