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
from app.tests.test_context import TestConfigKey

MISSION_GALILEO_HUBBLE = {
    "mission_id": "galileo_hubble",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 43.138, "y": 12.437}]}
}


class TestMissions(unittest.IsolatedAsyncioTestCase):
    """Test an end-to-end mission"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_mission_with_s3_map(self):
        """ Test a simple mission with an S3 map file example """
        robot_a = test_context.RobotInit("robot_a", 43.308, 18.642)
        async with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.MAP_FILE_S3),
                robots=[robot_a],
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

            mission = await mission_control_client.send_mission(MISSION_GALILEO_HUBBLE)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=1000)
                self.assertEqual(mission_state, "COMPLETED")

if __name__ == "__main__":
    unittest.main()
