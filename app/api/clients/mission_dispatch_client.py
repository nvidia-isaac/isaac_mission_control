# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import enum
import json
import time
from typing import Optional
from httpx import HTTPError

from app.api.clients.base_api_client import BaseAPIClient
from cloud_common.objects.robot import RobotObjectV1
from app.common.models import PickPlaceData, NVActionType, MultiObjectPickPlaceData


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
                                   actions: dict[str, list[int]], timeout_s: int, mission_id: Optional[str] = None):
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
            "timeout": timeout_s
        }
        if mission_id:
            data["name"] = mission_id
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_charging_mission(self, robot: str,
                                      docking_action: dict, timeout_s: int, mission_id: Optional[str] = None):
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
        if mission_id:
            data["name"] = mission_id
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_undock_mission(self, robot: str, timeout_s: int = 600,
                                    mission_id: Optional[str] = None):
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
        if mission_id:
            data["name"] = mission_id
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create mission.",
                                                 "Created mission.",
                                                 json=data)

    async def create_pickplace_mission(self, robot: str, pick_place_data: PickPlaceData,
                                       timeout_s: int = 600, mission_id: Optional[str] = None):
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
        if mission_id:
            data["name"] = mission_id
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create pickplace mission.",
                                                 "Created pickplace mission.",
                                                 json=data)

    async def create_multi_object_pickplace_mission(self, robot: str,
                                                    pickplace_data: MultiObjectPickPlaceData,
                                                    timeout_s: int = 600, mission_id: Optional[str] = None):
        self._logger.info("Sending multi-object pickplace mission to Mission Dispatch")
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]

        action_params = {
            "mode": pickplace_data.mode.value,
            "class_ids": ",".join(pickplace_data.class_ids),
            "target_poses": json.dumps(pickplace_data.target_poses.dict())
        }

        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": {
                        "action_type": "multi_object_pick_and_place",
                        "action_parameters": action_params
                    }
                }
            ],
            "timeout": timeout_s
        }

        if mission_id:
            data["name"] = mission_id
        self._logger.debug("Multi-object pickplace mission data: %s", data)
        return await self.make_request_with_logs("post", endpoint,
                                                 "Failed to create multi-object pickplace mission.",
                                                 "Created multi-object pickplace mission.",
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

    async def get_available_apriltags(self, robot: str):
        self._logger.info("Getting available AprilTags from Dispatch")

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        action = {
            "action_type": "get_apriltags",
            "action_parameters": {}
        }
        data = {
            "robot": robot,
            "mission_tree": [
                {
                    "action": action
                }
            ],
            "timeout": 300  # AprilTag detection might take some time
        }

        submission = await self.make_request_with_logs("post", endpoint,
                                                       "Failed to get available AprilTags",
                                                       "Retrieved available AprilTags.",
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

    async def enable_map_action(self, robots: list[RobotObjectV1], map_id: str, map_version: str = "", timeout_s: int = 600):
        """Trigger *enableMap* instant action on each robot."""
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)
        endpoint = self._base_url + self._endpoints["mission"]["path"]

        base_action = {
            "name": "enable_map",
            "action": {
                "action_type": NVActionType.ENABLE_MAP,
                "action_parameters": {
                    "mapId": map_id,
                    "mapVersion": map_version
                }
            }
        }

        robot_names = [robot.name for robot in robots]
        coros = []
        for robot_name in robot_names:
            data = {
                "robot": robot_name,
                "mission_tree": [base_action],
                "timeout": timeout_s
            }
            self._logger.debug("Enable map for %s: %s", robot_name, data)
            coros.append(
                self.make_request_with_logs(
                    "post", endpoint,
                    error_msg=f"Failed to enable map for robot: {robot_name}.",
                    success_msg=f"Sent enableMap for robot: {robot_name}.",
                    json=data,
                )
            )

        await asyncio.gather(*coros, return_exceptions=True)

    # Backwards-compatibility wrapper
    async def load_map_action(self, robots: list[RobotObjectV1], map_id: str, timeout_s: int):
        """Deprecated wrapper calling *enable_map_action*."""
        await self.enable_map_action(robots, map_id, timeout_s=timeout_s)

    async def download_map_action(
            self,
            robots: list[RobotObjectV1],
            map_id: str, map_version: str = "", map_download_link: str = "",
            map_hash: str | None = None, timeout_s: int = 600):
        """Trigger *downloadMap* instant action on each robot."""
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)
        endpoint = self._base_url + self._endpoints["mission"]["path"]

        params = {
            "mapId": map_id,
            "mapVersion": map_version,
            "mapDownloadLink": map_download_link
        }
        if map_hash is not None:
            params["mapHash"] = map_hash

        base_action = {
            "name": "download_map",
            "action": {
                "action_type": NVActionType.DOWNLOAD_MAP,
                "action_parameters": params
            }
        }

        coros = []
        for robot in robots:
            data = {
                "robot": robot.name,
                "mission_tree": [base_action],
                "timeout": timeout_s
            }
            coros.append(
                self.make_request_with_logs(
                    "post", endpoint,
                    error_msg=f"Failed to download map for robot: {robot.name}.",
                    success_msg=f"Sent downloadMap for robot: {robot.name}.",
                    json=data,
                )
            )

        await asyncio.gather(*coros, return_exceptions=True)

    async def delete_map_action(
            self, robots: list[RobotObjectV1],
            map_id: str, map_version: str = "", timeout_s: int = 600):
        """Trigger *deleteMap* instant action on each robot."""
        timeout_s = max(self._config["default_mission_timeout"], timeout_s)
        endpoint = self._base_url + self._endpoints["mission"]["path"]

        base_action = {
            "name": "delete_map",
            "action": {
                "action_type": NVActionType.DELETE_MAP,
                "action_parameters": {
                    "mapId": map_id,
                    "mapVersion": map_version
                }
            }
        }

        coros = []
        for robot in robots:
            data = {
                "robot": robot.name,
                "mission_tree": [base_action],
                "timeout": timeout_s
            }
            coros.append(
                self.make_request_with_logs(
                    "post", endpoint,
                    error_msg=f"Failed to delete map for robot: {robot.name}.",
                    success_msg=f"Sent deleteMap for robot: {robot.name}.",
                    json=data,
                )
            )

        await asyncio.gather(*coros, return_exceptions=True)

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
