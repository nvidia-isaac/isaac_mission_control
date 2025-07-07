# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("//bzl:python.bzl", "mission_control_py_library")
load("//bzl:python.bzl", "mission_control_py_test")
load("@io_bazel_rules_docker//python3:image.bzl", "py3_image")
load("@python_third_party//:requirements.bzl", "requirement")

mission_control_py_library(
    name="test_context",
    srcs=[
        "test_context.py",
    ],
    data=[
        "//app:mission-control-img-bundle",
        "//app/tests/test_utils:mission-database-img-bundle",
        "//app/tests/test_utils:mission-dispatch-img-bundle",
        "//app/tests/test_utils:mission-simulator-img-bundle",
        "//app/tests/test_utils:mosquitto-img-bundle",
        "//app/tests/test_utils:postgres-database-img-bundle",
        "//app/tests/test_utils:waypoint-graph-generator-img-bundle",
        "//app/tests/test_utils:cuopt-img-bundle",
        "//app/config:test_overrides.yaml",
        "//app/config:test_base.yaml"
    ],
    deps=[
        "//app/api",
        "//app/common",
        "//app/core",
        "//app/tests/test_utils",
        "//:cloud_common_objects",
        requirement("httpx"),
        requirement("pydantic"),
        requirement("requests"),
        requirement("pyyaml"),
    ]
)

mission_control_py_test(
    name="mission_test",
    size="large",
    srcs=[
        "mission_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="robotinventory_test",
    size="small",
    srcs=[
        "robotinventory_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="robot_test",
    size="large",
    srcs=[
        "robot_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="metropolis_test",
    size="large",
    srcs=[
        "metropolis_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="dock_test",
    size="large",
    srcs=[
        "dock_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="pickplace_test",
    size="large",
    srcs=[
        "pickplace_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="objectdetection_test",
    size="large",
    srcs=[
        "objectdetection_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "exclusive",
        "supports-graceful-termination"
    ],
)
