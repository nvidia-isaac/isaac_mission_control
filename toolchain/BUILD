"""
Copyright (c) 2025, NVIDIA CORPORATION. All rights reserved.

NVIDIA CORPORATION and its licensors retain all intellectual property
and proprietary rights in and to this software, related documentation
and any modifications thereto. Any use, reproduction, disclosure or
distribution of this software and related documentation without an express
license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

load(":cc_toolchain_config.bzl", "cc_toolchain_config")
cc_toolchain_config(name = "k8_gcc_9_toolchain_config")

filegroup(name = "empty")

cc_toolchain_suite(
    name = "clang_suite",
    toolchains = {
        "k8": ":cc-compiler-k8-gcc-9",
    },
)

cc_toolchain(
    name = "cc-compiler-k8-gcc-9",
    all_files = ":empty",
    compiler_files = ":empty",
    dwp_files = ":empty",
    linker_files = ":empty",
    objcopy_files = ":empty",
    strip_files = ":empty",
    supports_param_files = 0,
    toolchain_config = ":k8_gcc_9_toolchain_config",
    toolchain_identifier = "k8-toolchain-gcc-9",
)
