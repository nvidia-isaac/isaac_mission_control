# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Platform-specific OCI image tags: NVIDIA Isaac images use separate tags per arch
# (e.g. 4.3.0-amd64 vs 4.3.0-arm64). This extension creates unified repo names
# (mission_simulator_base, mission_simulator_base_linux_amd64, etc.) that select
# or alias to the correct per-tag oci pull repos.

def _platform_image_repo_impl(rctx):
    rctx.file("BUILD.bazel", rctx.attr.build_content)

_platform_image_repo = repository_rule(
    implementation = _platform_image_repo_impl,
    attrs = {"build_content": attr.string(mandatory = True)},
)

def _mission_control_oci_platform_extension_impl(module_ctx):
    # Each entry: (base_name, amd64_repo_target, arm64_repo_target)
    # Target inside an oci_pull repo has the same name as the repo.
    images = [
        ("mission_simulator_base", "mission_simulator_base_amd64_linux_amd64", "mission_simulator_base_arm64_linux_arm64"),
        ("mission_dispatch_base", "mission_dispatch_base_amd64_linux_amd64", "mission_dispatch_base_arm64_linux_arm64"),
        ("mission_database_base", "mission_database_base_amd64_linux_amd64", "mission_database_base_arm64_linux_arm64"),
        ("waypoint_graph_generator_base", "waypoint_graph_generator_base_amd64_linux_amd64", "waypoint_graph_generator_base_arm64_linux_arm64"),
    ]
    for base_name, amd64_repo, arm64_repo in images:
        # Repo that uses select() so @base_name resolves by current platform.
        # oci_pull puts the image target at repo root, so use //:target_name not //target_name.
        select_build = """
alias(
    name = "{base_name}",
    actual = select(
        {{
            "@platforms//cpu:x86_64": "@{amd64_repo}//:{amd64_repo}",
            "@platforms//cpu:arm64": "@{arm64_repo}//:{arm64_repo}",
        }},
        no_match_error = "mission_control_oci: no image for this platform (need linux/amd64 or linux/arm64)",
    ),
    visibility = ["//visibility:public"],
)
""".format(
            base_name = base_name,
            amd64_repo = amd64_repo,
            arm64_repo = arm64_repo,
        )
        _platform_image_repo(
            name = base_name,
            build_content = select_build,
        )
        # Per-platform alias repos so @base_name_linux_amd64 and @base_name_linux_arm64 keep working
        for repo_name, actual_repo in [
            (base_name + "_linux_amd64", amd64_repo),
            (base_name + "_linux_arm64", arm64_repo),
        ]:
            alias_build = """
alias(
    name = "{repo_name}",
    actual = "@{actual_repo}//:{actual_repo}",
    visibility = ["//visibility:public"],
)
""".format(
                repo_name = repo_name,
                actual_repo = actual_repo,
            )
            _platform_image_repo(
                name = repo_name,
                build_content = alias_build,
            )

mission_control_oci_platform = module_extension(
    implementation = _mission_control_oci_platform_extension_impl,
)
