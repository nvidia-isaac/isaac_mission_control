# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import unittest
import httpx

from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests import test_context


MISSION_A_EXACT_END_LOCATION = {
    "mission_id": "mission_a_exact_end_location",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 8, "y": 8}],
                     "end_location": {"x": 8.3421, "y": 10.1234, "theta": 1.23, "exact": True}}
}

MISSION_A_EXACT_NO_THETA = {
    "mission_id": "mission_a_exact_no_theta",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 8, "y": 8}],
                     "end_location": {"x": 8.3421, "y": 10.1234, "exact": True}}
}

class TestMissions(unittest.IsolatedAsyncioTestCase):
    """Test an end-to-end mission"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_exact_end_location(self):
        """ Test ending on exact location """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running & health endpoint has test coverage
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_mission(MISSION_A_EXACT_END_LOCATION)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

            # Check that the robot ended on the exact location
            # Using Mission simulator, we can assert the exact location.
            # However, in real world with nav2, there is a goal tolerance so it won't be exact.
            robot_object = await mission_database_client.get_robot("robot_a")
            self.assertEqual(robot_object.status.pose.x,
                             8.3421)
            self.assertEqual(robot_object.status.pose.y,
                             10.1234)
            self.assertEqual(robot_object.status.pose.theta,
                             1.23)

    async def test_exact_no_theta(self):
        """
        The mission should still navigate to the x, y if no theta is provided.
        """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running & health endpoint has test coverage
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_mission(MISSION_A_EXACT_NO_THETA)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

            robot_object = await mission_database_client.get_robot("robot_a")
            self.assertEqual(robot_object.status.pose.x,
                             8.3421)
            self.assertEqual(robot_object.status.pose.y,
                             10.1234)


if __name__ == "__main__":
    unittest.main()
