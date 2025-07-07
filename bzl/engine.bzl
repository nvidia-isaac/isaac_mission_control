load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def engine_workspace():
    """Loads external dependencies required to build apps with alice"""

    http_archive(
        name = "net_zlib_zlib",
        build_file = "//third_party:zlib.BUILD",
        sha256 = "c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1",
        url = "https://developer.nvidia.com/isaac/download/third_party/zlib-1-2-11-tar-gz",
        type = "tar.gz",
        strip_prefix = "zlib-1.2.11"
    )

    # Sample semantic maps
    http_archive(
        name = "sample_semantic_maps",
        url = "https://urm.nvidia.com/artifactory/sw-isaac-sdk-generic-local/dependencies/internal/data/sample_semantic_maps.tar.gz",
        sha256 = "6b51b29831737f185d704a8d495eabcb107abe7950d4f5475426c9494526a33a",
        type = "tgz",
        build_file_content = """
filegroup(
    name = "sample_semantic_maps",
    srcs = glob([
        "**/*",
    ]),
    visibility = ["//visibility:public"],
)
        """,
    )

    http_archive(
        name = "pybind11_bazel",
        strip_prefix = "pybind11_bazel-b162c7c88a253e3f6b673df0c621aca27596ce6b",
        urls = ["https://github.com/pybind/pybind11_bazel/archive/b162c7c88a253e3f6b673df0c621aca27596ce6b.zip"],
    )
    # We still require the pybind library.
    http_archive(
        name = "pybind11",
        build_file = "@pybind11_bazel//:pybind11.BUILD",
        strip_prefix = "pybind11-2.10.4",
        urls = ["https://github.com/pybind/pybind11/archive/v2.10.4.tar.gz"],
    )
    
    http_archive(
        name = "com_github_gflags_gflags",
        sha256 = "34af2f15cf7367513b352bdcd2493ab14ce43692d2dcd9dfc499492966c64dcf",
        strip_prefix = "gflags-2.2.2",
        urls = ["https://github.com/gflags/gflags/archive/v2.2.2.tar.gz"],
    )

    http_archive(
        name = "com_github_google_glog",
        sha256 = "122fb6b712808ef43fbf80f75c52a21c9760683dae470154f02bddfc61135022",
        strip_prefix = "glog-0.6.0",
        urls = ["https://github.com/google/glog/archive/v0.6.0.zip"],
    )

    http_archive(
        name = "boost",
        urls = ["https://urm.nvidia.com/artifactory/sw-isaac-sdk-generic-local/dependencies/third_party/boost-1.80.0.tar.gz"],
        build_file = "//third_party:boost.BUILD",
        strip_prefix = "boost_1_80_0",
    )
