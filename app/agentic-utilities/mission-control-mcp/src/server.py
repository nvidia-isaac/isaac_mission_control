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

Mission Control MCP Server

Provides a Model Context Protocol (MCP) server for interacting with Mission Control
to manage robots, submit missions, and visualize routes.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from .queries import MissionControlClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)

# Initialize the mission control client with environment variable support.
base_url = os.getenv("MISSION_CONTROL_URL", "http://localhost:8050")
mc_client = MissionControlClient(base_url)

# Create MCP server
server = Server("mission-control-mcp")
ROBOT_NAME_REQUIRED_DESCRIPTION = "Name of the robot (required)"
TOOL_TEST_CONNECTION = "test_mission_control_connection"
TOOL_SUBMIT_NAVIGATION = "submit_navigation_mission"
TOOL_SUBMIT_CHARGING = "submit_charging_mission"
TOOL_SUBMIT_UNDOCK = "submit_undock_mission"
TOOL_GET_DETECTED_OBJECTS = "get_detected_objects"
TOOL_GET_DETECTED_APRILTAGS = "get_detected_apriltags"
TOOL_VISUALIZE_ROUTE = "visualize_route"
TOOL_GET_MAP_INFO = "get_map_info"
TOOL_LIST_AVAILABLE_MAPS = "list_available_maps"
TOOL_SELECT_MAP = "select_map"
TOOL_DEPLOY_MAP_TO_ROBOT = "deploy_map_to_robot"
TOOL_SUBMIT_OBJECTIVE = "submit_objective"
TOOL_CANCEL_OBJECTIVE = "cancel_objective"
TOOL_SUBMIT_PICK_AND_PLACE = "submit_pick_and_place"


def _text_result(text: str, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=is_error)


def _require(arguments: dict, key: str) -> Any:
    value = arguments.get(key)
    if value is None or value == "":
        raise ValueError(f"Missing required argument: {key}")
    return value


def _unsupported_feature(feature: str) -> CallToolResult:
    return _text_result(f"Isaac Cloud MCP doesn't currently support {feature}.")


def format_mission_response(response: Dict) -> str:
    """Format mission submission response for display."""
    result = "**Mission Submitted Successfully**\n\n"

    if isinstance(response, dict):
        if "sub_mission_uuids" in response:
            result += f"- Sub-missions: {', '.join(response['sub_mission_uuids'])}\n"
        if "robots" in response:
            result += f"- Assigned robots: {', '.join(response['robots'])}\n"
        if "docks" in response and response["docks"]:
            result += f"- Docks: {', '.join(response['docks'])}\n"
        if "solver" in response:
            result += f"- Solver: {response['solver']}\n"
    else:
        result += f"- Response: {response}\n"

    return result


def format_waypoints(waypoints: List[Dict]) -> str:
    """Format waypoints for display."""
    lines = []
    for i, wp in enumerate(waypoints):
        lines.append(f"  {i+1}. ({wp.get('x', 0):.2f}, {wp.get('y', 0):.2f})")
    return "\n".join(lines) + ("\n" if lines else "")


@server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available MCP tools for Mission Control operations."""
    return ListToolsResult(
        tools=[
            Tool(
                name=TOOL_TEST_CONNECTION,
                description="Test connection to Mission Control API and show system status",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name=TOOL_SUBMIT_NAVIGATION,
                description=(
                    "Submit a navigation mission to send a robot through a series of waypoints"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "waypoints": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number", "description": "X coordinate"},
                                    "y": {"type": "number", "description": "Y coordinate"},
                                },
                                "required": ["x", "y"],
                            },
                            "description": "List of waypoints with x, y coordinates (required)",
                        },
                        "robot_name": {
                            "type": "string",
                            "description": (
                                "Specific robot to use (optional, auto-assigns if not provided)"
                            ),
                        },
                        "solver": {
                            "type": "string",
                            "enum": ["NVIDIA_CUOPT", "CPU_DIJKSTRA"],
                            "description": (
                                "Route optimization solver (optional, defaults to NVIDIA_CUOPT)"
                            ),
                        },
                        "iterations": {
                            "type": "integer",
                            "description": (
                                "Number of times to repeat the route (optional, default 1)"
                            ),
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Mission timeout in seconds (optional, default 3600)",
                        },
                    },
                    "required": ["waypoints"],
                },
            ),
            Tool(
                name=TOOL_SUBMIT_CHARGING,
                description="Send a robot to charge at a docking station",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": "Name of the robot to charge (required)",
                        },
                        "dock_id": {
                            "type": "string",
                            "description": (
                                "Specific dock ID to use (optional, "
                                "auto-selects nearest if not provided)"
                            ),
                        },
                    },
                    "required": ["robot_name"],
                },
            ),
            Tool(
                name=TOOL_SUBMIT_UNDOCK,
                description="Undock a robot from its current docking station",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": "Name of the robot to undock (required)",
                        }
                    },
                    "required": ["robot_name"],
                },
            ),
            Tool(
                name=TOOL_GET_DETECTED_OBJECTS,
                description="Get objects detected by a robot's camera",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": ROBOT_NAME_REQUIRED_DESCRIPTION,
                        }
                    },
                    "required": ["robot_name"],
                },
            ),
            Tool(
                name=TOOL_GET_DETECTED_APRILTAGS,
                description="Get AprilTags detected by a robot's camera",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": ROBOT_NAME_REQUIRED_DESCRIPTION,
                        }
                    },
                    "required": ["robot_name"],
                },
            ),
            Tool(
                name=TOOL_VISUALIZE_ROUTE,
                description=(
                    "Generate a visualization of a route on the map without submitting a mission"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "waypoints": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"},
                                    "y": {"type": "number"},
                                },
                                "required": ["x", "y"],
                            },
                            "description": "List of waypoints to visualize (required)",
                        },
                        "solver": {
                            "type": "string",
                            "enum": ["NVIDIA_CUOPT", "CPU_DIJKSTRA"],
                            "description": "Solver to use for route calculation (optional)",
                        },
                    },
                    "required": ["waypoints"],
                },
            ),
            Tool(
                name=TOOL_GET_MAP_INFO,
                description="Get information about the currently configured map",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name=TOOL_LIST_AVAILABLE_MAPS,
                description="List all maps that have been uploaded to Mission Control",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name=TOOL_SELECT_MAP,
                description="Activate an uploaded map for use in Mission Control",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "map_id": {
                            "type": "string",
                            "description": "ID of the map to activate (required)",
                        }
                    },
                    "required": ["map_id"],
                },
            ),
            Tool(
                name=TOOL_DEPLOY_MAP_TO_ROBOT,
                description="Download and enable a map on a specific robot",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": ROBOT_NAME_REQUIRED_DESCRIPTION,
                        },
                        "map_id": {
                            "type": "string",
                            "description": "ID of the map to deploy (required)",
                        },
                    },
                    "required": ["robot_name", "map_id"],
                },
            ),
            Tool(
                name=TOOL_SUBMIT_OBJECTIVE,
                description="Submit a behavior tree objective to Mission Control",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "objective": {
                            "type": "object",
                            "description": "Objective definition (required)",
                        }
                    },
                    "required": ["objective"],
                },
            ),
            Tool(
                name=TOOL_CANCEL_OBJECTIVE,
                description="Cancel a running objective",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "objective_name": {
                            "type": "string",
                            "description": "Name/ID of the objective to cancel (required)",
                        }
                    },
                    "required": ["objective_name"],
                },
            ),
            Tool(
                name=TOOL_SUBMIT_PICK_AND_PLACE,
                description="Submit a pick and place mission for a manipulator robot",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "robot_name": {
                            "type": "string",
                            "description": "Name of the manipulator robot (required)",
                        },
                        "object_id": {
                            "type": "integer",
                            "description": "ID of the object to pick (required)",
                        },
                        "class_id": {
                            "type": "string",
                            "description": "Class/type of the object (required)",
                        },
                        "pos_x": {"type": "number", "description": "Target X position (required)"},
                        "pos_y": {"type": "number", "description": "Target Y position (required)"},
                        "pos_z": {"type": "number", "description": "Target Z position (required)"},
                        "quat_x": {
                            "type": "number",
                            "description": "Orientation quaternion X (required)",
                        },
                        "quat_y": {
                            "type": "number",
                            "description": "Orientation quaternion Y (required)",
                        },
                        "quat_z": {
                            "type": "number",
                            "description": "Orientation quaternion Z (required)",
                        },
                        "quat_w": {
                            "type": "number",
                            "description": "Orientation quaternion W (required)",
                        },
                    },
                    "required": [
                        "robot_name",
                        "object_id",
                        "class_id",
                        "pos_x",
                        "pos_y",
                        "pos_z",
                        "quat_x",
                        "quat_y",
                        "quat_z",
                        "quat_w",
                    ],
                },
            ),
        ]
    )


def _handle_test_connection(_: dict) -> CallToolResult:
    health = mc_client.health_check()
    if health.get("api_accessible"):
        lines = [
            "**Mission Control Connection OK**",
            "",
            f"- API URL: {base_url}",
            "- Status: Healthy",
        ]
        if "response" in health:
            lines.append(f"- Response: {health['response']}")
        return _text_result("\n".join(lines) + "\n")

    lines = [
        "**Mission Control Connection Failed**",
        "",
        f"- API URL: {base_url}",
        f"- Error: {health.get('error', 'Unknown')}",
        "- Make sure the Mission Control service is running and reachable",
    ]
    return _text_result("\n".join(lines) + "\n", is_error=True)


def _handle_submit_navigation(arguments: dict) -> CallToolResult:
    waypoints = arguments.get("waypoints") or []
    if not isinstance(waypoints, list) or len(waypoints) < 1:
        return _text_result("Error: at least one waypoint is required.\n", is_error=True)

    response = mc_client.submit_navigation_mission(
        route=waypoints,
        solver=arguments.get("solver", "NVIDIA_CUOPT"),
        timeout=arguments.get("timeout", 3600),
        iterations=arguments.get("iterations", 1),
        robot_name=arguments.get("robot_name"),
    )

    result = "**Navigation Mission Submitted**\n\n"
    result += "**Waypoints:**\n"
    result += format_waypoints(waypoints) + "\n"
    result += format_mission_response(response)
    return _text_result(result)


def _handle_submit_charging(arguments: dict) -> CallToolResult:
    robot_name = _require(arguments, "robot_name")
    dock_id = arguments.get("dock_id")
    response = mc_client.submit_charging_mission(robot_name, dock_id)

    result = "**Charging Mission Submitted**\n\n"
    result += f"- Robot: {robot_name}\n"
    if dock_id:
        result += f"- Dock: {dock_id}\n"
    result += format_mission_response(response)
    return _text_result(result)


def _handle_submit_undock(arguments: dict) -> CallToolResult:
    robot_name = _require(arguments, "robot_name")
    response = mc_client.submit_undock_mission(robot_name)

    result = "**Undock Mission Submitted**\n\n"
    result += f"- Robot: {robot_name}\n"
    result += format_mission_response(response)
    return _text_result(result)


def _handle_detected_objects(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_GET_DETECTED_OBJECTS)


def _handle_detected_apriltags(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_GET_DETECTED_APRILTAGS)


def _handle_visualize_route(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_VISUALIZE_ROUTE)


def _handle_get_map_info(_: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_GET_MAP_INFO)


def _handle_list_maps(_: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_LIST_AVAILABLE_MAPS)


def _handle_select_map(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_SELECT_MAP)


def _handle_deploy_map(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_DEPLOY_MAP_TO_ROBOT)


def _handle_submit_objective(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_SUBMIT_OBJECTIVE)


def _handle_cancel_objective(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_CANCEL_OBJECTIVE)


def _handle_pick_and_place(arguments: dict) -> CallToolResult:
    return _unsupported_feature(TOOL_SUBMIT_PICK_AND_PLACE)


ToolHandler = Callable[[dict], CallToolResult]

_TOOL_HANDLERS: Dict[str, ToolHandler] = {
    TOOL_TEST_CONNECTION: _handle_test_connection,
    TOOL_SUBMIT_NAVIGATION: _handle_submit_navigation,
    TOOL_SUBMIT_CHARGING: _handle_submit_charging,
    TOOL_SUBMIT_UNDOCK: _handle_submit_undock,
    TOOL_GET_DETECTED_OBJECTS: _handle_detected_objects,
    TOOL_GET_DETECTED_APRILTAGS: _handle_detected_apriltags,
    TOOL_VISUALIZE_ROUTE: _handle_visualize_route,
    TOOL_GET_MAP_INFO: _handle_get_map_info,
    TOOL_LIST_AVAILABLE_MAPS: _handle_list_maps,
    TOOL_SELECT_MAP: _handle_select_map,
    TOOL_DEPLOY_MAP_TO_ROBOT: _handle_deploy_map,
    TOOL_SUBMIT_OBJECTIVE: _handle_submit_objective,
    TOOL_CANCEL_OBJECTIVE: _handle_cancel_objective,
    TOOL_SUBMIT_PICK_AND_PLACE: _handle_pick_and_place,
}


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    """Handle MCP tool calls."""
    try:
        logger.info("Calling tool %s with args: %s", name, arguments)
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return _text_result(f"Error: unknown tool: {name}\n", is_error=True)
        return handler(arguments or {})
    except ValueError as e:
        return _text_result(f"Error: {e}\n", is_error=True)
    except Exception as e:
        logger.exception("Error in tool %s", name)
        error_msg = str(e)
        if "Cannot connect" in error_msg:
            error_msg += "\n\nTroubleshooting:\n"
            error_msg += "- Check if Mission Control is running\n"
            error_msg += f"- Verify the API is accessible: `curl {base_url}/api/v1/health`\n"
            error_msg += "- Check that required dependencies are up\n"
        return _text_result(f"Error: {error_msg}\n", is_error=True)


async def _main_async() -> None:
    """Async main entry point for the MCP server."""
    logger.info("Starting Mission Control MCP server, connecting to %s", base_url)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mission-control-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    """Console-script entry point."""
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()

