# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2022-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

load("//bzl:python.bzl", "mission_control_py_library")
load("//bzl:python.bzl", "mission_control_py_test")
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
        "//app/config:test_base.yaml",
        "//app/config:map_dir"
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
        "local",
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
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name = "pydantic_v2_migration_test",
    size = "small",
    srcs = ["pydantic_v2_migration_test.py"],
    deps = [
        "//:cloud_common_objects",
        "//app/api",
        "//app/common",
        "//app/core",
        requirement("fastapi"),
        requirement("pydantic"),
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
        "local",
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
        "local",
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
        "local",
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
        "local",
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
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="objectives_test",
    size="large",
    srcs=[
        "objectives_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="objectives_context_test",
    size="large",
    srcs=[
        "objectives_context_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination",
    ],
)

mission_control_py_test(
    name="cuopt_test",
    size="large",
    srcs=[
        "cuopt_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="apriltag_test",
    size="large",
    srcs=[
        "apriltag_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="map_update_test",
    size="large",
    srcs=[
        "map_update_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="exact_end_location_test",
    size="large",
    srcs=[
        "exact_end_location_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)

mission_control_py_test(
    name="objectives_decorators_test",
    size="large",
    srcs=[
        "objectives_decorators_test.py",
    ],
    deps=[
        ":test_context",
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],    
)

mission_control_py_test(
    name="mission_control_mcp_test",
    size="large",
    srcs=[
        "mission_control_mcp_test.py",
    ],
    deps=[
        ":test_context",
        "//app:mission_control_mcp",
        requirement("httpx"),
        requirement("mcp"),
    ],
    tags=[
        "local",
        "exclusive",
        "supports-graceful-termination"
    ],
)
