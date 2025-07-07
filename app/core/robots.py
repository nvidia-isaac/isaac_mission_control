# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging

from typing import Optional
from cloud_common.objects.common import ICSUsageError
from cloud_common.objects.robot import RobotObjectV1


class RobotInventory:
    """ Inventory class """

    def __init__(self, robot_list: list[dict]):
        """ Start with list of robots we're allowed to use from config """
        self._robot_inventory: dict[str, RobotObjectV1] = {}
        self._robot_locations: dict[str, int] = {}
        if not robot_list:
            return
        for robot_data in robot_list:
            if "name" not in robot_data:
                raise ICSUsageError("Robot name is not defined in config")
            if "status" not in robot_data:
                robot_data["status"] = {}
            robot = RobotObjectV1(**robot_data)
            if robot.name in self._robot_inventory:
                raise KeyError(
                    f"Robot name {robot.name} already exists")
            self._robot_inventory[robot.name] = robot

    def set_robot_nodes(self, names: list[str], nodes: list):
        """ Setter for the WayPointGraph node IDs that
        are closest to the starting point for the robots """

        if len(names) != len(nodes):
            raise ICSUsageError(
                "The number of robot names and nodes should be the same.")

        for name, node in zip(names, nodes):
            if node is None or node < 0:
                raise ICSUsageError(
                    f"Robot: {name} Node: {node} is negative or null value")
            self._robot_locations[name] = node

    def get_robot(self, name: str):
        """ Accessor fn """
        return self._robot_inventory[name]

    def get_robots(self, names: Optional[list[str]] = None):
        """ Accessor fn """
        if names:
            return [self._robot_inventory[name] for name in names]
        else:
            return list(self._robot_inventory.values())

    def get_robot_names(self):
        """ Get robot names """
        return list(self._robot_inventory.keys())

    def get_robot_location(self, name: str):
        """ Get location node of robot.
        Return -1 if robot does not have a location node. """
        return self._robot_locations.get(name, -1)
