# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

FROM nvcr.io/nvidia/base/ubuntu:22.04_20240212
ARG DEBIAN_FRONTEND=noninteractive

# Install python
RUN apt update && \
    apt install -y ca-certificates curl software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt install -y bash python3.10 python3.10-dev python3.10-distutils

# Create symlinks
RUN if [ -L /usr/bin/python3 ]; then unlink /usr/bin/python3; fi && \
    ln -s /usr/bin/python3.10 /usr/bin/python3 && \
    ln -s /usr/bin/python3 /usr/bin/python

# Install pip using apt and upgrade
RUN apt install -y python3.10-venv python3-pip && \
    python3 -m pip install --upgrade pip

# Verify the installation
RUN python3 --version

# Install GCC
RUN apt upgrade -y
RUN apt install build-essential -y

# Install bash
RUN apt-get install -y bash

# Install Bazel
RUN apt-get install -y unzip
RUN curl -s -L https://github.com/bazelbuild/bazel/releases/download/6.1.2/bazel-6.1.2-installer-linux-x86_64.sh -o bazel.sh
RUN chmod +x bazel.sh
RUN bash bazel.sh

# Install docker
RUN apt-get install -y gnupg lsb-release git
RUN git config --global --add safe.directory '*'
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
RUN echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
RUN apt-get update
RUN apt-get install -y docker-ce-cli
