# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import httpx
import unittest

from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests import test_context
from app.tests.test_context import TestConfigKey
from cloud_common.objects.robot import VDA5050AgvClass


class TestObjectDetection(unittest.IsolatedAsyncioTestCase):
    """Ensure pick-place works for manipulators and fails for other robots;
    also, ensures navigation missions aren't sent to manipulators"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_objectdetection(self):
        """Ensure that pickplace works for manipulator robots"""
        robots = [test_context.RobotInit(
            "robot_a", 35, 35, battery=100, robot_type=VDA5050AgvClass.MANIPULATOR)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.PICKPLACE),
                robots=robots,
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online
            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            print("Object detection mission commencing.")
            await mission_control_client.send_objdetection_mission("robot_a")
            db_objdet_a = await ctx.mission_database_client.get_detection_results("robot_a")
            print("Detected objects: " + str(db_objdet_a.status.detected_objects))
            assert db_objdet_a.status.detected_objects[0].object_id == 0


if __name__ == "__main__":
    unittest.main()
