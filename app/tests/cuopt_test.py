import unittest
import asyncio
import httpx
import os

from app.api.clients.mission_control_client import MissionControlClient
from app.tests import test_context
from app.tests.test_context import TestConfigKey
from app.tests import test_utils

# pylint: disable=protected-access  # Accessing protected member for testing purposes

class TestCuOpt(unittest.IsolatedAsyncioTestCase):
    """Tests for cuOpt behaviour with and without CPU fallback."""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def _run_test(self, fallback_enabled: bool):
        """Helper to run charging mission test with given fallback setting."""
        # Set or clear env var before spinning up TestContext so that the
        # Mission-Control container inherits it.
        original_env = os.environ.get("MC_ENABLE_CPU_FALLBACK")
        if fallback_enabled:
            # Ensure variable not set to false
            os.environ.pop("MC_ENABLE_CPU_FALLBACK", None)
        else:
            os.environ["MC_ENABLE_CPU_FALLBACK"] = "false"

        try:
            robot_a = test_context.RobotInit("robot_a", 9.611, 14.6, battery=10)

            async with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.DOCKS),
                robots=[robot_a],
                async_client=self.client,
            ) as ctx:
                # Simulate cuOpt failure by killing the container.
                if hasattr(ctx, "_cuopt_container_id") and ctx._cuopt_container_id:
                    test_utils.kill_container(ctx._cuopt_container_id)
                    await asyncio.sleep(2)

                mission_control_client = MissionControlClient(
                    ctx.mission_control_config, client=self.client
                )

                mc_online = await mission_control_client.wait_for_mc_alive(timeout=120)
                self.assertTrue(mc_online, "Mission Control did not start in time.")

                if fallback_enabled:
                    mission = await mission_control_client.send_charging_mission("robot_a")
                    # Expect CPU_DIJKSTRA solver when fallback works
                    self.assertEqual(
                        mission.get("solver"),
                        "CPU_DIJKSTRA",
                        "Mission Control did not fall back to CPU_DIJKSTRA solver.",
                    )
                    self.assertGreater(len(mission.get("sub_mission_uuids", [])), 0)
                    for sub_uuid in mission["sub_mission_uuids"]:
                        state = await test_context.wait_for_mission_to_complete(
                            ctx, sub_uuid, timeout=900
                        )
                        self.assertEqual(state, "COMPLETED")
                else:
                    # Expect HTTP error because MC cannot route without cuOpt and fallback disabled
                    with self.assertRaises(httpx.HTTPError):
                        await mission_control_client.send_charging_mission("robot_a")
        finally:
            # Restore original env var to avoid cross-test contamination
            if original_env is None:
                os.environ.pop("MC_ENABLE_CPU_FALLBACK", None)
            else:
                os.environ["MC_ENABLE_CPU_FALLBACK"] = original_env

    async def test_fallback_enabled(self):
        """Verify graceful fallback works when env var is not set / true."""
        await self._run_test(fallback_enabled=True)

    async def test_fallback_disabled(self):
        """Verify failure when env var disables fallback."""
        await self._run_test(fallback_enabled=False)


if __name__ == "__main__":
    unittest.main()
