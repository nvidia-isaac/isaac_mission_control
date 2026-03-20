# Copyright (c) 2023-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import time
from typing import Any, Optional

from httpx import HTTPError

from app.api.clients.base_api_client import BaseAPIClient
from cloud_common.objects.detection_results import DetectionResultsObjectV1
from cloud_common.objects.apriltag_results import AprilTagResultsObjectV1
from cloud_common.objects.robot import RobotObjectV1, RobotStateV1
from cloud_common.objects.mission import MissionObjectV1
from cloud_common.objects.objective import ObjectiveV1, ObjectiveStateV1, ObjectiveStatusV1


class MissionDatabaseClient(BaseAPIClient):
    """ Mission Database API client """
    _config: dict = {}
    _endpoints: dict = {
        "robot": {
            "path": "/robot",
        },
        "mission": {
            "path": "/mission",
        },
        "detection_results": {
            "path": "/detection_results"
        },
        "apriltag_results": {
            "path": "/apriltag_results"
        },
        "objective": {
            "path": "/objective"
        },
        "health": {
            "path": "/health"
        }
    }

    async def get_robot(self, name: str, suppress_error_msg=False) -> RobotObjectV1:
        """ Get one robot by name from mission database """
        self._logger.info("Querying robot information from Mission Database API")

        endpoint_info = self._endpoints["robot"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + name

        robot = await self.make_request_with_logs("get",
                                                  endpoint,
                                                  success_msg="Successfully queried robot",
                                                  error_msg="Failed to query robot",
                                                  suppress_msg=suppress_error_msg)

        robot_obj = RobotObjectV1(**robot)
        self._logger.debug("Robot: %s", robot_obj)
        return robot_obj

    async def get_detection_results(self, name: str) -> DetectionResultsObjectV1:
        """ Get detection results by robot name from mission database """
        self._logger.info(
            "Querying detection results from Mission Database API")

        endpoint_info = self._endpoints["detection_results"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + name

        detector_object = await self.make_request_with_logs("get",
                                                            endpoint,
                                                            success_msg="Detection get success",
                                                            error_msg="Detection get failure")
        self._logger.info("Retrieved detection results from database")
        return DetectionResultsObjectV1(**detector_object)

    async def get_apriltag_results(self, name: str) -> AprilTagResultsObjectV1:
        """ Get AprilTag results by robot name from mission database """
        self._logger.info(
            "Querying AprilTag results from Mission Database API")

        endpoint_info = self._endpoints["apriltag_results"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + name

        apriltag_object = await self.make_request_with_logs("get",
                                                            endpoint,
                                                            success_msg="AprilTag get success",
                                                            error_msg="AprilTag get failure")
        self._logger.info("Retrieved AprilTag results from database")
        return AprilTagResultsObjectV1(**apriltag_object)

    async def get_robots(self, params: Optional[dict] = None) -> list[RobotObjectV1]:
        """ Get all robot objects in the mission database """
        #  Changed to debug instead of info to avoid spamming the logs
        self._logger.debug("Querying robot information from Mission Database API")

        endpoint_info = self._endpoints["robot"]
        endpoint = self._base_url + endpoint_info["path"]

        robots = []
        try:
            self._logger.debug("Filter: %s", params)
            robots = await self.make_request_with_logs("get",
                                                       endpoint,
                                                       success_msg="Successfully queried robots",
                                                       error_msg="Failed to query robots",
                                                       params=params)

        except HTTPError as exc:
            self._logger.warning(exc)
        robot_objs = [RobotObjectV1(**robot) for robot in robots]
        self._logger.debug("Robots: %s", str(robot_objs))
        return robot_objs

    async def get_mission(self, name: str) -> MissionObjectV1 | None:
        """ Get one mission by name from mission database """
        self._logger.info("Querying mission information from Mission Database API")

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + name

        try:
            mission = await self.make_request_with_logs("get",
                                                        endpoint,
                                                        success_msg="Successfully queried mission",
                                                        error_msg="Failed to query mission")
        except HTTPError as exc:
            self._logger.error(exc)
            return None
        mission_obj = MissionObjectV1(**mission)
        self._logger.debug("Mission: %s", mission_obj)
        return mission_obj

    async def get_missions(self, params: Optional[dict] = None) -> list[MissionObjectV1] | None:
        """ Get missions from mission database """
        self._logger.info("Querying mission information from Mission Database API")

        endpoint_info = self._endpoints["mission"]
        endpoint = self._base_url + endpoint_info["path"]

        missions = []
        try:
            missions = await self.make_request_with_logs("get",
                                                         endpoint,
                                                         success_msg="Successfully queried mission",
                                                         error_msg="Failed to query mission",
                                                         params=params)

        except HTTPError as exc:
            self._logger.error(exc)
            return None
        mission_objs = [MissionObjectV1(**mission) for mission in missions]
        self._logger.debug("Missions: %s", str(mission_objs))
        return mission_objs

    async def create_robot(self, robot: RobotObjectV1):
        """ Get robot data from the mission dispatch """
        self._logger.info("Creating robot %s.", robot.name)
        endpoint_info = self._endpoints["robot"]
        endpoint = self._base_url + endpoint_info["path"]

        data: dict[str, Any] = {"name": robot.name}
        if robot.labels:
            data["labels"] = robot.labels
        if robot.heartbeat_timeout:
            data["heartbeat_timeout"] = robot.heartbeat_timeout.seconds
        if robot.battery:
            data["battery"] = dict(robot.battery)
        await self.make_request_with_logs("post", endpoint,
                                          f"Failed to create robot {robot.name}.",
                                          f"Created robot {robot.name}",
                                          json=data)

    async def create_robot_if_new(self, robot: RobotObjectV1):
        """ Register new robot with Dispatch """
        try:
            await self.get_robot(robot.name, suppress_error_msg=True)
        except HTTPError:
            await self.create_robot(robot)
            return robot.name

    async def create_robots_if_new(self, robots: list[RobotObjectV1]):
        """ For robots in mission control config, register them with Dispatch """
        robot_coros = []
        for robot in robots:
            robot_coros.append(self.create_robot_if_new(robot))
        results = await asyncio.gather(*robot_coros, return_exceptions=True)
        for result, i in enumerate(results):
            if isinstance(result, Exception):
                self._logger.error("Failed to create robot: %s", robots[i].name)
        return results

    async def create_objective(self, name: Optional[str] = None) -> ObjectiveV1:
        """Create new objective"""
        data = {}
        if name:
            data["name"] = name
        endpoint_info = self._endpoints["objective"]
        endpoint = self._base_url + endpoint_info["path"]
        obj = await self.make_request_with_logs("post", endpoint,
                                                "Failed to create objective.",
                                                "Created objective",
                                                json=data)
        objective = ObjectiveV1(**obj)
        return objective

    async def get_objective(self, name: str) -> ObjectiveV1:
        """Get all objectives"""
        endpoint_info = self._endpoints["objective"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + name
        self._logger.debug(endpoint)
        obj = await self.make_request_with_logs("get", endpoint,
                                                "Failed to create objective.",
                                                "Created objective")
        objective = ObjectiveV1(**obj)
        return objective

    async def update_objective(self, objective: ObjectiveV1):
        """Update objective status"""
        data = {"status": objective.status.dict()}
        self._logger.debug("Objective status: %s", str(objective.status.dict()))
        endpoint_info = self._endpoints["objective"]
        endpoint = self._base_url + endpoint_info["path"] + "/" + objective.name
        return await self.make_request_with_logs("put", endpoint,
                                                 "Failed to update objective.",
                                                 "Updated objective",
                                                 json=data)

    async def wait_for_objective_to_complete(self, objective_id: str, timeout=600):
        """ Returns True if objective is complete """
        end_time = time.time() + timeout
        while time.time() < end_time:
            obj = await self.get_objective(objective_id)
            if obj.status.state == ObjectiveStateV1.COMPLETED:
                self._logger.debug("Objective %s completed", objective_id)
                return True
            elif obj.status.state == ObjectiveStateV1.FAILED:
                self._logger.warning("Objective %s failed", objective_id)
                return False
            await asyncio.sleep(1)
        self._logger.warning("Objective %s did not complete within %s seconds",
                             objective_id, timeout)
        return False

    async def wait_for_robots(self, robots: list[str], timeout=60):
        """ Returns True if robots are online and IDLE before timeout """
        end_time = time.time() + timeout
        while time.time() < end_time:
            robot_objs = await self.get_robots(params={"names": robots})
                
            # Check if all robots are online and idle   
            all_ready = True
            for robot in robot_objs:
                if not (robot.status.online and robot.status.state == RobotStateV1.IDLE):
                    all_ready = False
                    break
                        
            if all_ready:
                return True
                
            await asyncio.sleep(1)
        return False

    async def health(self, suppress_error_msg=False):
        endpoint_info = self._endpoints["health"]
        endpoint = self._base_url + endpoint_info["path"]
        try:
            await self.make_request_with_logs("get", endpoint,
                                              "Failed to get health.",
                                              "Mission Dispatch Internal is online.",
                                              suppress_msg=suppress_error_msg)
        except HTTPError:
            return False
        return True

    async def poll_health(self, timeout=120, freq=1):
        self._logger.debug("Polling Mission Dispatch Internal Health")
        start_time = time.time()
        while time.time() - start_time < timeout:
            wpg_online = await self.health(suppress_error_msg=True)
            if wpg_online:
                self._logger.debug("Mission Dispatch Internal is reachable")
                return True
            await asyncio.sleep(1/freq)
        self._logger.error("Mission Dispatch Internal cannot be reached")
        return False
