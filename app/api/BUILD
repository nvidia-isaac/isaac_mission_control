# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

load("@rules_python//python:defs.bzl", "py_library")
load("@python_third_party//:requirements.bzl", "requirement")

py_library(
    name = "api",
    srcs = [
        "endpoints/mission_control_api.py",
        "endpoints/sap_api.py",
        "clients/base_api_client.py",
        "clients/cuopt_client.py",
        "clients/cuopt_service_client.py",
        "clients/esp_client.py",
        "clients/mas_client.py",
        "clients/metropolis_client.py",
        "clients/mission_control_client.py",
        "clients/mission_database_client.py",
        "clients/mission_dispatch_client.py",
        "clients/ota_file_service_client.py",
        "clients/waypoint_graph_generator_client.py",
        "clients/s3_client.py",
        "clients/sap_ewm_client.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//app/common",
        "//:cloud_common_objects",
        requirement("httpx"),
        requirement("numpy"),
        requirement("pydantic"),
        requirement("requests"),
        requirement("scipy"),
        requirement("boto3"),
    ],
) 