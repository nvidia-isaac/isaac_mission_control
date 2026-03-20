# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

FROM nvcr.io/nvidia/base/ubuntu:jammy-20251013
#FROM nvcr.io/nvidia/base/ubuntu:22.04_20240212
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

# Install Bazel (architecture-aware)
ARG TARGETARCH
RUN apt-get install -y wget
RUN if [ "$TARGETARCH" = "arm64" ]; then \
      wget --progress=dot:mega https://github.com/bazelbuild/bazel/releases/download/8.4.2/bazel-8.4.2-linux-arm64 -O /usr/bin/bazel; \
    else \
      wget --progress=dot:mega https://github.com/bazelbuild/bazel/releases/download/8.4.2/bazel-8.4.2-linux-x86_64 -O /usr/bin/bazel; \
    fi
RUN chmod +x /usr/bin/bazel

# Install docker and nvidia-container-toolkit
RUN apt-get update
RUN apt-get install -y gnupg lsb-release git
RUN git config --global --add safe.directory '*'
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
RUN echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
  
# Install NVIDIA Container Toolkit
RUN distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
    && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

RUN apt-get update
RUN apt-get install -y docker-ce-cli nvidia-container-toolkit
