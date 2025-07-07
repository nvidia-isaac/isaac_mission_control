# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import contextlib
import socket
import time

# How often to poll to see if a port is open
PORT_CHECK_PERIOD = 0.1


def check_port_open(port: int, host: str = "localhost") -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as test_socket:
        return test_socket.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: float = float("inf"), host: str = "localhost"):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if check_port_open(host=host, port=port):
            print(f"Host:Port {host}:{port} is open")
            return True
        time.sleep(PORT_CHECK_PERIOD)
    raise ValueError(f"Port {host}:{port} did not open in time")
