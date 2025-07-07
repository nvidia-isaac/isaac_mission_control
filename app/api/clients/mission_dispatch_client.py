# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import enum
import time

from httpx import HTTPError

from app.api.clients.base_api_client import BaseAPIClient
from cloud_common.objects.robot import RobotObjectV1
from app.common.models import PickPlaceData, NVActionType


class MissionDispatchClient(BaseAPIClient):

    """ Mission Dispatch API client """
    _config: dict = {}
    _endpoints: dict = {
        "mission": {
            "path": "/mission",
            "fields": {
                "robot",
                "mission_tree",
                "timeout"
            }
        },
        "robot": {
            "path": "/robot",
            "fields": {
                "name",
                "labels",
                "heartbeat_timeout"
            }
        },
        "health": {
            "path": "/health"
        }
    }

    async def send_tree_direct(self, robot: str, mission_tree: list):
        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        data = {
            "robot": robot,
            "mission_tree": mission_tree,
            "timeout": self._config["default_mission_timeout"]
        }
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_route_mission(self, robot: str, waypoints: list[dict],
                                   actions: dict[str, list[int]], timeout_s: int):
        """
        Create a mission following a provided route by building a mission tree and submitting
            the mission.
        Input: unique mission id string, robot name, list of nodes for the robot's route, a
            dict of action types to their node indices, and a timeout limit in seconds
        Returns: response json resulting from submitting the mission
        """
        self._logger.info("Sending mission to Mission Dispatch")
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]

        if NVActionType.PAUSE_ORDER in actions:
            mission_tree = []
            action_node: dict = {"action": {
                "action_type":  NVActionType.PAUSE_ORDER,
                "action_parameters": {}
            }}
            # Seperate waypoints to different route nodes based on action indexes.
            action_idx = [-1] + actions[NVActionType.PAUSE_ORDER]
            for i in range(1, len(action_idx)):
                route_node: dict = {
                    "route": {"waypoints": waypoints[action_idx[i-1]+1:action_idx[i]+1]}}
                mission_tree.append(route_node)
                mission_tree.append(action_node)
            if action_idx[-1] + 1 < len(waypoints):
                mission_tree.append(
                    {"route": {"waypoints": waypoints[action_idx[-1]+1:]}})
        else:
            mission_tree = [
                {"route": {"waypoints": waypoints}}]
        self._logger.debug("Mission tree: %s", mission_tree)
        data = {
            "robot": robot,
            "mission_tree": mission_tree,
            "timeout": timeout_s,
        }
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_charging_mission(self, robot: str,
                                      docking_action: dict, timeout_s: int):
        """
        Creates a mission for the robot to go to its charger.
        Input: robot name, route nodes, docking action, timeout in seconds
        Output: response json from submitting the mission
        """
        self._logger.info("Sending charging mission to Mission Dispatch")
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": docking_action
                }
            ],
            "timeout": timeout_s
        }
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_undock_mission(self, robot: str, timeout_s: int):
        self._logger.info("Sending undock mission to Mission Dispatch")
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        action = {
            "action_type": "undock_robot",
            "action_parameters": {}
        }
        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": action
                }
            ],
            "timeout": timeout_s
        }
        self._logger.debug(data)
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_pickplace_mission(self, robot: str, pick_place_data: PickPlaceData,
                                       timeout_s: int):
        self._logger.info("Sending pickplace mission to Mission Dispatch")
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]

        place_pose_str = f"{pick_place_data.pos_x}, {pick_place_data.pos_y}, {pick_place_data.pos_z}, " + \
            f"{pick_place_data.quat_x}, {pick_place_data.quat_y}, {pick_place_data.quat_z}, " + \
            f"{pick_place_data.quat_w}"

        action = {
            "action_type": "pick_and_place",
            "action_parameters": {
                "object_id": pick_place_data.object_id,
                "class_id": pick_place_data.class_id,
                "place_pose": place_pose_str
            }
        }
        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": action
                }
            ],
            "timeout": timeout_s
        }
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create pickplace mission.",
                                                 "Created pickplace mission.",
                                                 json=data)

    async def get_available_objects(self, robot: str):
        self._logger.info("Getting available objects from Dispatch")

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        action = {
            "action_type": "get_objects",
            "action_parameters": {}
        }
        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": action
                }
            ],
            "timeout": 300  # Object detection might take some time
        }

        submission = await self.make_request_with_logs("post", endpoint,
                                                       "Failed to get available objects",
                                                       "Retrieved available objects.",
                                                       json=data)

        return submission

    async def cancel_mission(self, name: str) -> dict:
        """ Cancel a mission by name from mission database """
        self._logger.info("Cancel mission %s", name)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + \
            endpoint_info["path"] + "/" + name + "/cancel"

        try:
            cancelled_mission = await self.make_request_with_logs("post",
                                                                  endpoint,
                                                                  success_msg="Cancelled mission",
                                                                  error_msg="Failed cancel mission")
        except HTTPError as exc:
            self._logger.warning(exc)
        return cancelled_mission

    async def load_map_action(self, robots: list[RobotObjectV1], map_id: str, timeout_s: int):
        """ Sends a map loading action for each robot """
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)
        endpoint = self._base_url + self._endpoints["mission"]["path"]
        data = {
            "robot": "",
            "mission_tree": [
                {
                    "name": "map_loading",
                    "action": {
                            "action_type": NVActionType.LOAD_MAP,
                            "action_parameters": {
                                "map_id": map_id
                            }
                    }
                }

            ],
            "timeout": timeout_s
        }
        robot_names = [robot.name for robot in robots]
        robot_coros = []
        for robot_name in robot_names:
            data["robot"] = robot_name
            self._logger.debug(
                "Post map loading action for robot: %s, \n %s", robot_name, data)
            error_msg = f"Failed to load map for robot: {robot_name}."
            success_msg = f"Sent map loading action for robot: {robot_name}."
            robot_coros.append(self.make_request_with_logs("post", endpoint,
                                                           error_msg,
                                                           success_msg,
                                                           json=data))
        results = await asyncio.gather(*robot_coros, return_exceptions=True)
        for result, i in enumerate(results):
            if isinstance(result, Exception):
                self._logger.error("Failed to load map for %s", robot_names[i])

    async def health(self, suppress_error_msg=False):
        endpoint_info = self._endpoints["health"]
        endpoint = self._base_url + endpoint_info["path"]
        try:
            await self.make_request_with_logs("get", endpoint,
                                              "Failed to get health",
                                              "Mission Dispatch is online",
                                              suppress_msg=suppress_error_msg)
        except HTTPError:
            return False
        return True

    async def poll_health(self, timeout=120, freq=1):
        self._logger.debug("Polling Mission Dispatch Health")
        start_time = time.time()
        while time.time() - start_time < timeout:
            wpg_online = await self.health(suppress_error_msg=True)
            if wpg_online:
                self._logger.debug("Mission Dispatch is reachable")
                return True
            await asyncio.sleep(1/freq)
        self._logger.error("Mission Dispatch cannot be reached")
        return False
