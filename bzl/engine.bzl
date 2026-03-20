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
