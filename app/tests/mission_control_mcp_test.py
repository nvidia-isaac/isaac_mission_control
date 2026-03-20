#!/usr/bin/env python3
"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""

import httpx
import unittest
import asyncio

from mcp.types import CallToolResult, TextContent
from src import server as mcp_server
from app.tests import test_context
from app.api.clients.mission_database_client import MissionDatabaseClient


SUPPORTED_TOOLS = {
    "test_mission_control_connection",
    "submit_navigation_mission",
    "submit_charging_mission",
    "submit_undock_mission",
}

UNSUPPORTED_TOOLS = [
    "get_detected_objects",
    "get_detected_apriltags",
    "visualize_route",
    "get_map_info",
    "list_available_maps",
    "select_map",
    "deploy_map_to_robot",
    "submit_objective",
    "cancel_objective",
    "submit_pick_and_place",
]

def _result_text(result: CallToolResult) -> str:
    assert result.content, "Expected tool result content to be non-empty"
    first = result.content[0]
    assert isinstance(first, TextContent), f"Expected TextContent, got {type(first)}"
    return first.text


class TestMissionControlMcpTools(unittest.IsolatedAsyncioTestCase):
    """Integration tests for Mission Control MCP tool handlers."""

    def _point_mcp_server_to_test_context(self, ctx: test_context.TestContext) -> None:
        base_url = ctx.mission_control_config["base_url"]
        mcp_server.base_url = base_url
        mcp_server.mc_client.base_url = base_url

    async def _wait_for_mission_control_ready(
        self, client: httpx.AsyncClient, timeout_s: float = 60.0
    ) -> None:
        """Wait until Mission Control health endpoint reports ready."""
        assert mcp_server.base_url, "Mission Control base URL must be set before readiness check"
        deadline = asyncio.get_running_loop().time() + timeout_s
        health_url = f"{mcp_server.base_url}/api/v1/health"
        last_error = ""

        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(health_url)
                if response.status_code == 200:
                    return
                last_error = f"status={response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            await asyncio.sleep(0.5)

        self.fail(f"Mission Control did not become ready in {timeout_s}s ({last_error})")

    async def _wait_for_robot_state(
        self,
        *,
        client: httpx.AsyncClient,
        mission_database_base_url: str,
        robot_name: str,
        expected_state: str,
        timeout_s: float = 60.0,
    ) -> None:
        """Wait until a robot reaches the expected Mission DB state."""
        deadline = asyncio.get_running_loop().time() + timeout_s
        robot_url = f"{mission_database_base_url}/robot/{robot_name}"
        last_state = "unknown"

        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(robot_url)
                if response.status_code == 200:
                    payload = response.json()
                    last_state = str(payload.get("status", {}).get("state", "unknown"))
                    if last_state == expected_state:
                        return
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(0.5)

        self.fail(
            f"Robot {robot_name} did not reach state {expected_state} in {timeout_s}s "
            f"(last_state={last_state})"
        )

    async def test_list_tools_contains_supported_and_unsupported(self) -> None:
        tools_result = await mcp_server.list_tools()
        names = {tool.name for tool in tools_result.tools}

        for tool_name in SUPPORTED_TOOLS:
            self.assertIn(tool_name, names)

        for tool_name in UNSUPPORTED_TOOLS:
            self.assertIn(tool_name, names)

    async def test_supported_tools_against_real_mission_control(self) -> None:
        client = httpx.AsyncClient(timeout=60.0)
        original_base_url = mcp_server.base_url
        original_client_base_url = mcp_server.mc_client.base_url
        try:
            async with test_context.TestContext(async_client=client, config_overrides=None) as ctx:
                self._point_mcp_server_to_test_context(ctx)
                await self._wait_for_mission_control_ready(client)

                # Wait for robot_a to be online and have pose in the database
                mission_database_client = MissionDatabaseClient(
                    ctx.mission_database_config, client=client
                )
                robots_ready = await mission_database_client.wait_for_robots(
                    robots=["robot_a"], timeout=60.0
                )
                self.assertTrue(
                    robots_ready,
                    "robot_a did not become online and IDLE before timeout",
                )

                result = await mcp_server.call_tool("test_mission_control_connection", {})
                self.assertFalse(result.isError)
                self.assertIn("Mission Control Connection OK", _result_text(result))

                nav_result = await mcp_server.call_tool(
                    "submit_navigation_mission",
                    {
                        "waypoints": [{"x": 26.0, "y": 26.0}],
                        "robot_name": "robot_a",
                        "solver": "CPU_DIJKSTRA",
                    },
                )
                self.assertFalse(nav_result.isError)
                self.assertIn("Navigation Mission Submitted", _result_text(nav_result))

                # Wait for the dispatched navigation mission to finish so undock can be accepted.
                await self._wait_for_robot_state(
                    client=client,
                    mission_database_base_url=ctx.mission_database_config["base_url"],
                    robot_name="robot_a",
                    expected_state="IDLE",
                    timeout_s=120.0,
                )

                undock_result = await mcp_server.call_tool(
                    "submit_undock_mission",
                    {"robot_name": "robot_a"},
                )
                self.assertFalse(undock_result.isError)
                self.assertIn("Undock Mission Submitted", _result_text(undock_result))
        finally:
            mcp_server.base_url = original_base_url
            mcp_server.mc_client.base_url = original_client_base_url
            await client.aclose()

    async def test_unsupported_tools_return_consistent_message(self) -> None:
        for tool_name in UNSUPPORTED_TOOLS:
            result = await mcp_server.call_tool(tool_name, {})
            self.assertFalse(result.isError, f"{tool_name} unexpectedly returned an error")
            self.assertEqual(
                _result_text(result),
                f"Isaac Cloud MCP doesn't currently support {tool_name}.",
            )

    async def test_unknown_tool_returns_error(self) -> None:
        result = await mcp_server.call_tool("does_not_exist", {})
        self.assertTrue(result.isError)
        self.assertIn("Error: unknown tool: does_not_exist", _result_text(result))


if __name__ == "__main__":
    unittest.main()
