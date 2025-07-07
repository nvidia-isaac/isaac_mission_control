# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import time

from httpx import HTTPError

from app.api.clients.base_api_client import BaseAPIClient
from app.common.models import MissionData, PickPlaceData


class MissionControlClient(BaseAPIClient):
    """ Mission Control API client """
    _endpoints: dict = {
        "mission": {
            "path": "/api/v1/mission/submit_mission",
            "fields": {
                "mission_id",
                "mission_template"
            }
        },
        "charging": {
            "path": "/api/v1/mission/charging",
            "fields": {
                "robot_name"
            }
        },
        "update_map": {
            "path": "/api/v1/update_map",
            "fields": {
                "map_uri",
                "force_replan"
            }
        },
        "health": {
            "path": "/api/v1/health"
        },
        "pickplace": {
            "path": "/api/v1/mission/pick_and_place",
            "fields": {
                "robot_name"
            }
        },
        "obj_detection": {
            "path": "/api/v1/mission/get_available_objects",
            "fields": {
                "robot_name"
            }
        },
        "submit_objective": {
            "path": "/api/v1/submit_objective",
        },
        "cancel_objective": {
            "path": "/api/v1/cancel_objective",
        },
        "visualize_route": {
            "path": "/api/v1/visualize_route",
        },
    }

    async def is_mc_alive(self):
        """ Call self health endpoint """
        self._logger.info("Checking if Mission Control is alive")
        endpoint_info = self._endpoints["health"]
        endpoint = self._base_url + endpoint_info["path"]
        try:
            await self.make_request_with_logs("get", endpoint, "Mission Control: Error",
                                              "Mission Control: Running")
        except HTTPError as e:
            self._logger.error("MC not alive: %s", str(e))
            return False
        return True

    async def wait_for_mc_alive(self, timeout=60):
        """ Waits for MC to start up """
        end_time = time.time() + timeout
        while time.time() < end_time:
            mc_alive = await self.is_mc_alive()
            if mc_alive:
                return True
            await asyncio.sleep(1)
        return False

    async def send_mission(self, mission: dict):
        """ Prepares information from the map and calls the Mission Dispatch API endpoint """
        self._logger.info("Sending mission from mission control")
        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]
        self._logger.debug("Mission control data: ")
        self._logger.debug(mission)

        api_fields = self._endpoints["mission"]["fields"]
        params = {k: v for k, v in mission.items() if k in api_fields}
        structured_mission = MissionData(**mission["mission_data"]).dict()
        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Mission control accepted mission",
                                                   params=params, json=structured_mission)
        return result

    async def send_charging_mission(self, robot_name: str):
        """ Send a single robot on a charging mission """
        self._logger.info("Sending charging mission from mission control")
        endpoint_info = self._endpoints["charging"]
        endpoint = self._base_url + endpoint_info["path"]
        self._logger.debug("Robot to be charged: %s", robot_name)
        params = {"robot_name": robot_name}
        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Mission control accepted charging mission",
                                                   params=params)
        return result

    async def send_pickplace_mission(self, robot_name: str, object_id: int, class_id: str,
                                     pos_x: float, pos_y: float, pos_z: float,
                                     quat_x: float, quat_y: float, quat_z: float, quat_w: float):
        """ Send a single robot on a pickplace mission """
        self._logger.info("Sending pickplace mission from mission control")
        endpoint_info = self._endpoints["pickplace"]
        endpoint = self._base_url + endpoint_info["path"]
        self._logger.debug("Robot to do pickplace: %s", robot_name)
        params = {"robot_name": robot_name}
        pick_place_data = PickPlaceData(object_id=object_id, class_id=class_id,
                                        pos_x=pos_x, pos_y=pos_y, pos_z=pos_z,
                                        quat_x=quat_x, quat_y=quat_y, quat_z=quat_z, quat_w=quat_w)

        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Mission control accepted pickplace mission",
                                                   params=params, json=pick_place_data.dict())
        return result

    async def send_objdetection_mission(self, robot_name: str):
        """ Give obj_detection mission to single robot """
        self._logger.info("Sending obj_detection mission from mission control")
        endpoint_info = self._endpoints["obj_detection"]
        endpoint = self._base_url + endpoint_info["path"]
        self._logger.debug("Robot doing object detection: %s", robot_name)
        params = {"robot_name": robot_name}
        result = await self.make_request_with_logs("get", endpoint, "Mission control error",
                                                   "Mission control accepted obj detection mission",
                                                   params=params)
        return result

    async def update_map(self, map_uri: str, force_replan: bool = False):
        """ Updates map and replan ongoing missions """
        self._logger.info("Updating map")
        endpoint_info = self._endpoints["update_map"]
        endpoint = self._base_url + endpoint_info["path"]
        params = {"map_uri": map_uri,
                  "force_replan": force_replan}
        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Update map success",
                                                   params=params)
        return result

    async def submit_objective(self, objective: dict):
        self._logger.info("Submitting objective to Mission Control")
        endpoint_info = self._endpoints["submit_objective"]
        endpoint = self._base_url + endpoint_info["path"]
        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Objective submission success", json=objective)
        return result
    
    async def cancel_objective(self, objective_name: str):
        self._logger.info("Cancelling objective")
        endpoint_info = self._endpoints["cancel_objective"]
        endpoint = self._base_url + endpoint_info["path"]
        result = await self.make_request_with_logs("post", endpoint, "Mission control error",
                                                   "Objective cancellation success", params={"objective_name": objective_name})
        return result

    async def visualize_route(self, mission_data: MissionData):
        """
        Visualize a route without creating an actual mission.
        Returns an image with the route drawn on the map.
        
        Args:
            mission_data: The mission data containing the route to visualize
            
        Returns:
            bytes: PNG image data
        """
        self._logger.info("Requesting route visualization image")
        endpoint_info = self._endpoints["visualize_route"]
        endpoint = self._base_url + endpoint_info["path"]
        
        try:
            async with self._client.post(
                endpoint, 
                json=mission_data.dict(),
                headers={"Accept": "image/png"}
            ) as response:
                response.raise_for_status()
                return await response.read()
        except Exception as e:
            self._logger.error(f"Route visualization error: {str(e)}")
            raise
