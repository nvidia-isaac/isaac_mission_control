# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import unittest
import httpx
from app.tests import test_context
from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests.test_context import TestConfigKey
from cloud_common.objects.robot import VDA5050AgvClass
from cloud_common.objects.apriltag_results import DetectedAprilTag
from cloud_common.objects.common import ICSUsageError


class TestAprilTagDetection(unittest.IsolatedAsyncioTestCase):
    """Test suite for AprilTag detection functionality"""

    async def asyncSetUp(self):
        # 10 s connect / 120 s read timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=120.0)
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_apriltagdetection_basic_flow(self):
        """Ensure that AprilTag detection works for manipulator robots"""
        robots = [test_context.RobotInit(
            "robot_a", 35, 35, battery=100, robot_type=VDA5050AgvClass.MANIPULATOR)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(
                    TestConfigKey.PICKPLACE),
                robots=robots,
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online, "Mission Control should be online"

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online, "Robot should be online and ready"

            print("AprilTag detection mission commencing.")

            # Send AprilTag detection mission and verify it's accepted
            mission_result = await mission_control_client.send_apriltag_detection_mission("robot_a")
            assert mission_result is not None, "Mission submission should return a result"

            # Get AprilTag results from database
            db_apriltag_a = await ctx.mission_database_client.get_apriltag_results("robot_a")
            print("Detected AprilTags: " +
                  str(db_apriltag_a.status.detected_apriltags))

            # Validate basic structure - pydantic models handle field validation automatically
            assert isinstance(db_apriltag_a.status.detected_apriltags, list), \
                "detected_apriltags should be a list"

            # Verify each detected AprilTag is a proper DetectedAprilTag instance
            for apriltag in db_apriltag_a.status.detected_apriltags:
                assert isinstance(apriltag, DetectedAprilTag), \
                    f"Each AprilTag should be a DetectedAprilTag instance, got {type(apriltag)}"

    async def test_apriltagdetection_robot_offline_error(self):
        """Test that AprilTag detection fails gracefully when robot is offline"""
        robots = [test_context.RobotInit(
            "robot_offline", 35, 35, battery=100, robot_type=VDA5050AgvClass.MANIPULATOR)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(
                    TestConfigKey.PICKPLACE),
                robots=robots,
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online, "Mission Control should be online"

            # Try to send mission to non-existent robot - should handle gracefully
            with self.assertRaises((ICSUsageError, KeyError, httpx.HTTPError)):
                await mission_control_client.send_apriltag_detection_mission(
                    "nonexistent_robot")


if __name__ == "__main__":
    unittest.main()
