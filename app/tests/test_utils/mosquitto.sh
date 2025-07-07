#!/bin/sh
# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

CONFIG_FILE=/mosquitto.conf

if [ $# != 2 ] ; then
    echo "usage: $0 <tcp_port> <websocket_port>"
    exit 1
fi
PORT=$1
PORT_WEBSOCKET=$2

echo "allow_anonymous true" > $CONFIG_FILE
echo "listener $PORT 0.0.0.0" >> $CONFIG_FILE
echo "listener $PORT_WEBSOCKET" >> $CONFIG_FILE
echo "protocol websockets" >> $CONFIG_FILE
mosquitto -c $CONFIG_FILE
