# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import httpx
import unittest
from datetime import datetime, timedelta

from app.common.models import MissionData
from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests import test_context
from app.tests.test_context import TestConfigKey
from cloud_common import objects

MISSION_TELEOP: dict = {
    "mission_id": "teleop",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"start_location": {"x": 20.3, "y": 10.1},
                     "end_location": {"x": 20.3, "y": 10.1},
                     "route": [{"x": 21.5, "y": 8.9},
                               {"x": 20.3, "y": 10.1},
                               {"x": 22,   "y": 10.1}
                               ],
                     "iterations": 2,
                     "teleop": [0, 1]
                     }
}


class TestRobot(unittest.IsolatedAsyncioTestCase):
    """Test battery query filter """

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_battery_query(self):
        """ Validate battery """
        additional_robots = [test_context.RobotInit("robot_b", 35, 35, battery=100),
                             test_context.RobotInit("robot_c", 25, 25, battery=10.0)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.ROBOTS),
                robots=additional_robots,
                async_client=self.client) as ctx:
            # Wait for robot a to be ready
            robota_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robota_online
            # Wait for robot b to be ready
            robotb_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_b"])
            assert robotb_online
            # Wait for robot c to be ready
            robotc_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_c"])
            assert robotc_online

            all_robots = await ctx.mission_database_client.get_robots()
            assert len(all_robots) == 3, str(all_robots)
            params = {
                "min_battery": 20.0
            }
            available_robots = await ctx.mission_database_client.get_robots(params)
            assert len(available_robots) == 2, str(available_robots)

    async def test_battery_spec(self):
        robots = [test_context.RobotInit("robot_b", 35, 35, battery=100)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.ROBOTS),
                robots=robots,
                async_client=self.client) as ctx:
            robots_config = ctx.config.get_robots_config()
            # Wait for robot a to be ready
            robota_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robota_online
            robot = await ctx.mission_database_client.get_robot("robot_a")
            cfg_spec = robots_config[0]["battery"]
            assert robot.battery.critical_level == cfg_spec["critical_level"]
            assert robot.battery.recommended_minimum == cfg_spec["recommended_minimum"]
            assert robot.battery.recommended_maximum == cfg_spec["recommended_maximum"]

            # Wait for robot b to be ready
            robotb_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_b"])
            assert robotb_online
            robot = await ctx.mission_database_client.get_robot("robot_b")
            cfg_spec = robots_config[1]["battery"]
            # default should be 10
            assert robot.battery.critical_level == 10.0
            assert robot.battery.recommended_minimum == cfg_spec["recommended_minimum"]
            assert robot.battery.recommended_maximum is None

    async def test_teleop(self):
        """ Test a simple mission with teleop """
        with test_context.TestContext(
                config_overrides=None,  # Use base config
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                ctx.mission_control_config, self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)
            # Verify Control is running & health endpoint has test coverage
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online
            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            assembled_mission = MissionData(
                **MISSION_TELEOP["mission_data"]).get_assembled_mission()
            self.assertEqual(
                assembled_mission.actions["pause_order"], [1, 2, 4, 5])

            mission = await mission_control_client.send_mission(MISSION_TELEOP)
            timeout = 900

            for robot, sub_mission_uuid in zip(mission["robots"], mission["sub_mission_uuids"]):
                start_time = datetime.now()
                end_time = start_time + timedelta(seconds=timeout)
                mission_state = objects.mission.MissionStateV1.PENDING.value
                while datetime.now() < end_time:
                    watch_mission = \
                        objects.MissionObjectV1(
                            **await ctx.mission_dispatch_client.make_request_with_logs(
                                "get", ctx.mission_dispatch_client.base_url + "/mission/" +
                                sub_mission_uuid, "Mission not found", "Mission found"))

                    if watch_mission.status.state.done:
                        mission_state = watch_mission.status.state.value
                        break

                    watch_robot = objects.RobotObjectV1(
                        **await ctx.mission_dispatch_client.make_request_with_logs(
                            "get", ctx.mission_dispatch_client.base_url + "/robot/" + robot,
                            "Robot not found", "Robot found"))
                    # Check the robot is in teleop mode
                    if watch_robot.status.state == objects.robot.RobotStateV1.TELEOP:
                        # Stop teleop
                        await ctx.mission_dispatch_client.make_request_with_logs(
                            "post", ctx.mission_dispatch_client.base_url +
                            "/robot/" + robot + "/teleop",
                            "Stop teleop error", "Stop teleop request sent",
                            params={"params": objects.robot.RobotTeleopActionV1.STOP.value})

                self.assertEqual(mission_state, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
