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

load("//bzl:python.bzl", "mission_control_py_binary")
load("//bzl:python.bzl", "mission_control_py_library")
load("@python_third_party//:requirements.bzl", "requirement")

mission_control_py_library(
    name = "mission_control_mcp",
    srcs = [
        "agentic-utilities/mission-control-mcp/src/__init__.py",
        "agentic-utilities/mission-control-mcp/src/queries.py",
        "agentic-utilities/mission-control-mcp/src/server.py",
    ],
    imports = ["agentic-utilities/mission-control-mcp"],
    visibility = ["//visibility:public"],
    deps = [
        requirement("mcp"),
        requirement("requests"),
    ],
)

mission_control_py_binary(
    name = "mission-control",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//visibility:public"],
    deps = [
        "//app/api",
        "//app/common",
        "//app/core",
        "//app/core/objectives",
        requirement("fastapi"),
        requirement("uvicorn"),
        requirement("pydantic"),
        requirement("httpx"),
        requirement("opentelemetry-api"),
        requirement("opentelemetry-sdk"),
        requirement("opentelemetry-instrumentation-fastapi"),
        requirement("opentelemetry-exporter-otlp-proto-grpc"),
        requirement("numpy"),
        requirement("scipy"),
        requirement("requests"),
        requirement("python-multipart"),
    ],
    data = [
        "//app/config:map_dir",
    ]
)
