# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import enum
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any
import boto3
import pydantic
import requests
import httpx
import os
import io
from PIL import Image, ImageDraw
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import py_trees
import app.api.clients.esp_client as esp
import app.api.clients.metropolis_client as metropolis
from app.api.clients.cuopt_client import CuOptClient
from app.api.clients.mas_client import MASServiceClient
from app.common.metrics import Telemetry, Timeframe
from app.core.mission_control_config import MissionControlConfig
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.api.clients.mission_dispatch_client import MissionDispatchClient
from app.api.clients.ota_file_service_client import OTAFileServiceClient
from app.api.clients.s3_client import S3Client
from app.core.robots import RobotInventory
from app.core.task import Task
from app.common.utils import (
    Point,
    angle_between_points,
)
from datetime import datetime

from app.api.clients.waypoint_graph_generator_client import (
    WaypointGraphGeneratorClient
)
from app.common.waypoint_graph import WaypointGraph
from app.common.models import (
    MissionData, SolverType, MissionType, MissionDataExtend,
    PickPlaceData, RouteVisualizationData
)
from app.core.objective_behavior_tree import ObjectiveBehaviorTree, ObjectiveLeafNode

from cloud_common import objects
from cloud_common.objects.mission import MissionStateV1
from cloud_common.objects.robot import RobotObjectV1, RobotStateV1
from cloud_common.objects.common import ICSServerError, ICSUsageError
from cloud_common.objects.objective import ObjectiveV1, ObjectiveStateV1, ObjectiveNodeType, ObjectiveNode

from app.core.sap_ewm_background import SapEwmBackgroundTask


class MissionControl:
    """ Class to orchestrate all isaac microservices """
    _instance = None
    sap_background_task: Optional[SapEwmBackgroundTask] = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if not MissionControl._instance:
            raise ICSServerError("MC app not started.")
        return MissionControl._instance

    def __init__(self, config: MissionControlConfig, async_client: httpx.AsyncClient,
                 otel_meters: Optional[dict] = None):
        """  Mission Control Initialization """
        self.logger = logging.getLogger("Isaac Mission Control")
        self.config = config
        self.wpg_client = WaypointGraphGeneratorClient(config.get_wpg_config(), async_client)
        if not config.get_ota_config():
            self.ota_client = None
        else:
            self.ota_client = OTAFileServiceClient(config.get_ota_config(), async_client)
        self.cuopt_client = CuOptClient(config.get_cuopt_config(), async_client)
        self.mission_dispatch_client = MissionDispatchClient(
            config.get_mission_dispatch_config(), async_client)
        self.mission_database_client = MissionDatabaseClient(
            config.get_mission_database_config(), async_client)
        self.robots = RobotInventory(config.get_robots_config())
        self.wpg_cache: WaypointGraph = None  # type: ignore
        self.constants = config.constants
        self.metropolis_client = None
        self.esp_client = None
        self.mas_client = None
        self.otel_meters = otel_meters
        self.telemetry = Telemetry(config.get_metrics_config()["SEND_TELEMETRY"],
                                   ssa_client_id=config.get_metrics_config()[
            "TELEMETRY_ID"],
            ssa_client_secret=config.get_metrics_config()[
            "TELEMETRY_SECRET"],
            metrics_env=config.get_metrics_config()["TELEMETRY_ENV"])

        self.telemetry.add_kpi(
            name="mission_control_boots", value=1, frequency=Timeframe.RUNTIME)

        metropolis_config = config.get_metropolis_config()
        if metropolis_config:
            self.metropolis_client = metropolis.MetropolisClient(
                metropolis_config, async_client)
        esp_config = config.get_esp_config()
        if esp_config:
            self.esp_client = esp.ESPServiceClient(esp_config, async_client)
        mas_config = config.get_mas_config()
        if mas_config:
            self.mas_client = MASServiceClient(mas_config, async_client)
        s3_config = config.get_s3_config()
        self.s3_client = S3Client(s3_config["AWS_ACCESS_KEY_ID"],
                                  s3_config["AWS_SECRET_ACCESS_KEY"],
                                  s3_config["AWS_REGION"],
                                  s3_config["AWS_ENDPOINT_URL"])
        self.initialized = False
        MissionControl._instance = self
        
        # Initialize SAP background task only if enabled in config
        if config.get_sap_config().enable_sap_ewm:
            MissionControl.sap_background_task = SapEwmBackgroundTask(self)
        else:
            MissionControl.sap_background_task = None

    async def startup(self):
        """ Mission Control FastAPI Startup fn """
        self.logger.info("Beginning FastAPI startup")
        map_config = self.config.get_map_config()
        map_config.apply_metadata_yaml()

        # Check that all dependencies are up before starting Mission Control
        results = await asyncio.gather(
            self.mission_dispatch_client.poll_health(timeout=self.constants.STARTUP_TIMEOUT),
            self.mission_database_client.poll_health(timeout=self.constants.STARTUP_TIMEOUT),
            self.wpg_client.poll_health(timeout=self.constants.STARTUP_TIMEOUT)
        )
        if False in results:
            raise ICSServerError("Mission Control dependencies did not come up in time")

        self.wpg_cache = await self.wpg_client.request_new_graph()

        # TODO: Investigate - Creating robots this way will cause missing robots in Dispatch occasionally
        # results = await self.mission_database_client.create_robots_if_new(self.robots.get_robots())
        results = []
        for robot in self.robots.get_robots():
            new_robot = await self.mission_database_client.create_robot_if_new(robot)
            results.append(new_robot)
            await asyncio.sleep(0.25)
        self.logger.info("Robots created: %s", str(results))
        
        # Register SAP robots during startup
        if self.config.get_sap_config().enable_sap_ewm:
            try:
                sap_robots_count = await self.register_sap_robots()
                self.logger.info(f"Registered {sap_robots_count} SAP robots during startup")
            except Exception as e:
                self.logger.error(f"Failed to initialize SAP robots during startup: {e}")

        # Start SAP background task if enabled
        if self.sap_background_task:
            self.logger.info("Starting SAP background task")
            await self.sap_background_task.start()
        
        # Continue with map loading    
        if (map_config.map_file or map_config.map_uri) and map_config.metadata:
            if self.ota_client:
                map_url = map_config.map_file if map_config.map_file else map_config.map_uri
                response = requests.get(map_url, timeout=30)
                self.ota_client.ota_file_upload(
                    map_config.metadata.dict(), map_content=response.content)
            if map_config.push_map_on_startup:
                await self.mission_dispatch_client.load_map_action(
                    self.robots.get_robots(), json.dumps([map_config.metadata.map_id]),
                    timeout_s=600)

        self.logger.info("Mission Control config:\n"  # pylint: disable=logging-fstring-interpolation
                         f"Map file: {map_config.map_file}\n"
                         f"Map uri: {map_config.map_uri}\n"
                         f"Map s3: {map_config.map_s3}\n"
                         f"X offset: {map_config.metadata.x_offset}\n"
                         f"Y offset: {map_config.metadata.y_offset}\n"
                         f"Rotation: {map_config.metadata.rotation}\n"
                         f"safety_distance: {map_config.metadata.safety_distance}\n"
                         f"Robots: {self.robots.get_robot_names()}")
        self.initialized = True
        self.logger.info("Ending FastAPI startup")

    async def reset_wpg_cache(self):
        self.wpg_cache = await self.wpg_client.request_new_graph()

    async def update_task(self, task: Task, target_locations: list[int]):
        """ Prepare tasks using target_location and wpg_cache """
        if None in target_locations:
            self.logger.error("WPG returned None for get_nearest_nodes: "
                              "Non-navigable surface in mission plan")
            raise ValueError("Non-navigable surface in mission plan")

        # Update task nodes.
        node_locations = self.wpg_cache.nodes
        try:
            world_frame_locations = [node_locations[node]
                                     for node in target_locations]

        except IndexError as exc:
            raise ValueError(
                "Target location requested that's out of bounds") from exc

        task_nodes = await self.wpg_client.get_nearest_nodes(world_frame_locations)
        self.logger.debug("Node_locations: %s", str(task_nodes))

        max_weight = self.wpg_cache.get_maximum_weight()
        task.set_task_nodes(task_nodes, max_weight)

    async def update_robot_nodes(self, database_robots: list[RobotObjectV1]):
        """ Set WPG node IDs for given robots and return robots from inventory """
        robot_positions_world = [robot.status.pose
                                 for robot in database_robots]
        robot_nodes = await self.wpg_client.get_nearest_nodes(robot_positions_world)
        available_names = [robot.name for robot in database_robots]
        self.robots.set_robot_nodes(available_names, robot_nodes)
        if None in robot_nodes or 0 in robot_nodes:
            self.logger.error(
                "One or more of your Robots is currently out of bounds")
        available_robots = self.robots.get_robots(names=available_names)
        return available_robots

    async def _calculate_route(self, mission_data: MissionData, mandatory_robot: Optional[RobotObjectV1] = None):
        """
        Calculate route based on mission data using either Dijkstra or cuOpt solver.
        
        Args:
            mission_data: The MissionData object containing route information
            mandatory_robot: Optional robot to use for the mission
            
        Returns:
            tuple: (ret_val, msg, target_locations, assembled_mission)
                - ret_val: Boolean indicating if the route calculation was successful
                - msg: Result message from the solver containing the calculated route
                - target_locations: List of node IDs corresponding to the waypoints
                - assembled_mission: The assembled mission object
        """
        task = Task()
        self.logger.debug("Creating route for mission data: %s", mission_data)
        
        # Get assembled mission and target locations
        assembled_mission = mission_data.get_assembled_mission()
        target_locations = await self.wpg_client.get_nearest_nodes(
            [point.dict() for point in assembled_mission.points])
        
        self.logger.debug("Target locations: %s", target_locations)
        
        if None in target_locations:
            self.logger.error("WPG returned None for get_nearest_nodes: Non-navigable surface in mission plan")
            raise objects.common.ICSServerError("Non-navigable surface in mission plan")
        
        # Update task with target locations
        await self.update_task(task, target_locations)
        
        # Get available robots
        available_robots = []
        if mandatory_robot:
            robot_from_db = await self.mission_database_client.get_robot(mandatory_robot.name)
            available_robots = await self.update_robot_nodes([robot_from_db])
        else:
            params = {
                "names": self.robots.get_robot_names(),
                "state": "IDLE",
                "online": True,
                "min_battery": self.constants.MIN_BATTERY,
                "position_initialized": True,
            }
            database_robots = await self.mission_database_client.get_robots(params)
            if not database_robots:
                raise objects.common.ICSServerError("No robots available for mission assignment")
            available_robots = await self.update_robot_nodes(database_robots)
        
        # Calculate routing and send to mission dispatch based on solver type
        ret_val = True
        msg = {}
        
        if mission_data.solver == SolverType.NVIDIA_CUOPT:
            robot_locations = [self.robots.get_robot_location(robot.name)
                               for robot in available_robots]
            ret_val, msg = await self.cuopt_client.optimize_graph(available_robots,
                                                                 robot_locations,
                                                                 task,
                                                                 self.wpg_cache)
        elif mission_data.solver == SolverType.CPU_DIJKSTRA:
            msg = self.optimize_graph_cpu(
                available_robots, task, self.wpg_cache)
        else:
            raise objects.common.ICSUsageError("Unknown Optimizer requested")
        
        self.logger.debug("Route calculation result: %s", msg)
        
        return ret_val, msg, target_locations, assembled_mission

    async def submit_navigation_mission(self, mission_id: str,
                                      mission_data: MissionData,
                                      mandatory_robot: Optional[RobotObjectV1] = None):
        """ Create a new mission and execute it """
        t_start = datetime.now()
        self.logger.debug("Received new mission:\n %s \n %s \n", mission_id,
                          mission_data)

        # Use common route calculation logic
        try:
            ret_val, msg, target_locations, assembled_mission = await self._calculate_route(
                mission_data, mandatory_robot)
            
            self.telemetry.add_kpi(name="number_of_target_locations",
                               value=len(target_locations), frequency=Timeframe.MISSION)
            
            if ret_val is True:
                msg["actions"] = assembled_mission.actions
                tmp_m_create = await self._create_missions(
                    msg, self.wpg_cache, mission_data, MissionType.SIMPLE_NAVIGATION, mission_id)
                t_end = datetime.now()
                t_diff = t_end - t_start

                # This only captures if the mission creation was completed.
                # Dispatch contains the final disposition of the mission.
                self.logger.debug("Mission generation time: %d",
                              t_diff.total_seconds())
                self.telemetry.add_kpi(name="mission_generation_time",
                                   value=t_diff.total_seconds(), frequency=Timeframe.MISSION)
                self.telemetry.add_kpi(
                    name="state", value="Completed", frequency=Timeframe.MISSION)

                self.telemetry.transmit_telemetry(self.telemetry.get_kpis_by_frequency(Timeframe.MISSION))
                self.telemetry.clear_frequency(Timeframe.MISSION)
                if self.otel_meters:
                    try:
                        meter = self.otel_meters.get("mission.generation.duration")
                        meter.record(t_diff.total_seconds(),  # type: ignore[union-attr]
                                     attributes={
                                         "success": True
                        })
                    except Exception as e:  # pylint: disable=broad-except
                        self.logger.error("Error when uploading metrics: %s", e)
                return tmp_m_create
            else:
                t_end = datetime.now()
                t_diff = t_end - t_start
                self.telemetry.add_kpi(name="mission_generation_time",
                                   value=t_diff.total_seconds(), frequency=Timeframe.MISSION)
                self.telemetry.add_kpi(
                    name="state", value="Failed", frequency=Timeframe.MISSION)

                self.telemetry.transmit_telemetry(self.telemetry.get_kpis_by_frequency(Timeframe.MISSION))
                self.telemetry.clear_frequency(Timeframe.MISSION)

                if self.otel_meters:
                    try:
                        meter = self.otel_meters.get("mission.generation.duration")
                        meter.record(t_diff.total_seconds(),  # type: ignore[union-attr]
                                     attributes={
                                         "success": False
                                     })
                    except Exception as e:  # pylint: disable=broad-except
                        self.logger.error("Error when uploading metrics: %s", e)
                raise objects.common.ICSServerError("Mission not accepted: "+msg)
        except Exception as e:
            t_end = datetime.now()
            t_diff = t_end - t_start
            self.telemetry.add_kpi(name="mission_generation_time",
                               value=t_diff.total_seconds(), frequency=Timeframe.MISSION)
            self.telemetry.add_kpi(
                name="state", value="Failed", frequency=Timeframe.MISSION)
            self.telemetry.transmit_telemetry(self.telemetry.get_kpis_by_frequency(Timeframe.MISSION))
            self.telemetry.clear_frequency(Timeframe.MISSION)
            
            if self.otel_meters:
                try:
                    meter = self.otel_meters.get("mission.generation.duration")
                    meter.record(t_diff.total_seconds(),  # type: ignore[union-attr]
                                 attributes={"success": False})
                except Exception as e_metric:  # pylint: disable=broad-except
                    self.logger.error("Error when uploading metrics: %s", e_metric)
            
            self.logger.error("Error calculating route: %s", str(e))
            raise e

    async def submit_charging_mission(self, mission_id: str,
                                      robot: RobotObjectV1,
                                      dock_id: Optional[str] = None):
        """ Create a new charging mission and execute it """

        self.logger.info("Creating charging mission")
        map_config = self.config.get_map_config()
        using_docks_config = len(map_config.docks) > 0

        robot_from_db = await self.mission_database_client.get_robot(robot.name)
        robot_to_charge = await self.update_robot_nodes([robot_from_db])
        robot_location = [self.robots.get_robot_location(robot_to_charge[0].name)]

        mission_data = MissionData(route=[Point(x=robot_from_db.status.pose.x,
                                                y=robot_from_db.status.pose.y)])

        task = Task()
        # Get task and docks list
        if using_docks_config:
            docks = map_config.docks
            dock_positions = [dock.dock_pose.get_staging_pose()
                              for dock in docks]
            dock_nodes = await self.wpg_client.get_nearest_nodes(dock_positions)
            task.set_task_locations_with_demand_and_prizes(dock_nodes)

        # Add detailed logging before the optimize_graph call
        self.logger.info("=== OPTIMIZATION DETAILS ===")
        self.logger.info(f"Robot to charge: {[r.name for r in robot_to_charge]}")
        self.logger.info(f"Robot location: {robot_location}")
        self.logger.info(f"Task locations: {task.task_locations}")
        self.logger.info(f"WPG cache nodes count: {len(self.wpg_cache.nodes)}")
        self.logger.info(f"WPG cache edges count: {len(self.wpg_cache.edges)}")

        # Time the operation
        start_time = time.time()
        self.logger.info(f"Starting optimization at {datetime.now().isoformat()}")

        msg = {}
        if dock_id:
            # Use user provided dock id
            dock = None
            ret_val = True
            for curr_dock in docks:
                if curr_dock.dock_id == dock_id:
                    dock = curr_dock
            if not dock:
                raise ICSUsageError(f"Dock {dock_id} does not exist")
            # Dummy vehicle_data for charging mission
            msg["vehicle_data"] = {}
            msg["vehicle_data"][robot.name] = {}
            msg["vehicle_data"][robot.name]["route"] = []
            msg["vehicle_data"][robot.name]["type"] = []
            msg["vehicle_data"][robot.name]["task_id"] = []
        else:
            # Use cuopt or dijkstra to find the optimal dock
            try:
                if mission_data.solver == SolverType.NVIDIA_CUOPT:
                    ret_val, msg = await asyncio.wait_for(
                        self.cuopt_client.optimize_graph(
                            robot_to_charge,
                            robot_location,
                            task,
                            self.wpg_cache,
                            robot_capacities=[1]
                        ),
                        timeout=30  # Set a reasonable timeout (adjust as needed)
                    )
                elif mission_data.solver == SolverType.CPU_DIJKSTRA:
                    ret_val = True
                    msg = self.optimize_graph_cpu(
                        robot_to_charge, task, self.wpg_cache)
                else:
                    raise objects.common.ICSUsageError("Unknown Optimizer requested")

                end_time = time.time()
                self.logger.info(f"Optimization completed in {end_time - start_time:.2f} seconds")
                self.logger.info(f"Optimization result: {ret_val}")
                self.logger.info(f"Optimization message: {msg}")
            except asyncio.TimeoutError:
                self.logger.error(
                    f"Optimization timed out after {time.time() - start_time:.2f} seconds")
                raise ICSServerError("Route optimization for charging mission timed out.")
            except Exception as e:
                self.logger.error(f"Optimization failed with exception: {str(e)}")
                self.logger.error(f"Exception details:", exc_info=True)
                raise ICSServerError(f"Route optimization for charging mission failed: {str(e)}")
            # Inside task_id, cuopt will return the list of tasks completed in sequence
            # Index 0 will always be 'Depot', and the rest will be the index of the task
            dock_index = int(msg["vehicle_data"][robot.name]["task_id"][1])
            self.logger.debug("Dock index: %s", dock_index)
            dock = docks[dock_index]

        msg["dockingAction"] = {
            "action_type": "dock_robot",
            "action_parameters": {
                "dock_id": dock.dock_id,
                "dock_type": dock.dock_type,
                "dock_pose": dock.dock_pose.to_parameter_str()
            }
        }

        self.logger.debug("Ready to create mission")
        if ret_val is True:
            return await self._create_missions(
                msg, self.wpg_cache, mission_data, MissionType.CHARGING, mission_id)
        else:
            raise ValueError("Mission not accepted: "+msg)


    async def submit_pickplace_mission(self, mission_id: str,
                                       robot: RobotObjectV1, pick_place_data: PickPlaceData):
        """ Create a new pick and place mission and execute it """
        self.logger.info("Creating pickplace mission")
        db_robot = await self.mission_database_client.get_robot(robot.name)
        if not db_robot:
            raise ICSUsageError(f"No robot named {robot.name}")
        if not db_robot.status.online:
            raise ICSServerError(f"Robot {robot.name} is not online")
        if db_robot.status.factsheet.agv_class != "FORKLIFT":
            raise ICSUsageError(f"Robot {robot.name} is not an arm.")
        mission_data = MissionData(route=[])
        mission_data_extend = MissionDataExtend(**mission_data.dict())
        submission = await self.mission_dispatch_client.create_pickplace_mission(
            robot.name, pick_place_data, 600)
        mission_data_extend.sub_mission_uuids.append(submission["name"])
        mission_data_extend.robots.append(robot.name)
        return mission_data_extend

    async def submit_undock_mission(self, robot: RobotObjectV1):
        """ Create a new undock mission and execute it """
        self.logger.info("Creating undock mission")

        db_robot = await self.mission_database_client.get_robot(robot.name)
        if not db_robot:
            raise ICSUsageError(f"No robot named {robot.name}")
        if not db_robot.status.online:
            raise ICSServerError(f"Robot {robot.name} is not online")
        if db_robot.status.state == RobotStateV1.ON_TASK:
            raise ICSServerError(f"Robot {robot.name} is running")

        mission_data = MissionData(route=[])
        mission_data_extend = MissionDataExtend(**mission_data.dict())
        submission = await self.mission_dispatch_client.create_undock_mission(
            robot.name, timeout_s=mission_data.timeout)
        mission_data_extend.sub_mission_uuids.append(submission["name"])
        mission_data_extend.robots.append(robot.name)
        return mission_data_extend

    async def _create_missions(self, msg: dict, graph: WaypointGraph, mission_data: MissionData,
                               mission_type: MissionType, mission_id: str):
        """ Create Behavior trees and send to Mission Dispatch """
        vehicle_data = msg["vehicle_data"]
        self.logger.debug("Vehicle_data: %s", str(vehicle_data))
        nodes = graph.nodes
        mission_data_extend = MissionDataExtend(**mission_data.dict())

        for robot, mission in vehicle_data.items():
            waypoints = []
            from_node = Point(x=0, y=0, z=0)
            for i, node in enumerate(mission["route"]):
                to_node = Point(x=nodes[node]["x"],
                                y=nodes[node]["y"],
                                z=0)
                theta = round(angle_between_points(from_node, to_node), 4)
                waypoints.append(objects.common.Pose2D(
                    x=nodes[node]["x"],
                    y=nodes[node]["y"],
                    theta=theta,
                    map_id=graph.map_id,
                    allowedDeviationXY=0 if mission["type"][i] == "Delivery" else 1,
                    allowedDeviationTheta=3.14).dict())
                from_node = to_node
            if len(waypoints) > 1:
                waypoints[0]["theta"] = waypoints[1]["theta"]

            if mission_type == MissionType.SIMPLE_NAVIGATION:
                submission = await self.mission_dispatch_client.create_route_mission(
                    robot, waypoints, msg["actions"], timeout_s=mission_data.timeout)
            elif mission_type == MissionType.CHARGING:
                submission = await self.mission_dispatch_client.create_charging_mission(
                    robot, msg["dockingAction"], timeout_s=mission_data.timeout)
                dock_id = msg["dockingAction"]["action_parameters"]["dock_id"]
                mission_data_extend.docks.append(dock_id)
            else:
                raise TypeError("Invalid Mission Type")
            mission_data_extend.sub_mission_uuids.append(submission["name"])
            mission_data_extend.robots.append(robot)
        return mission_data_extend

    def shortest_path(self, matrix_graph, source, destination):
        """
        Given a source/destination and CSR, compute the shortest path
        """
        if source == destination:
            return [source]
        # Run Dijkstra's algorithm: we don't use distances now
        _, predecessors = dijkstra(
            matrix_graph, indices=source, return_predecessors=True)

        # Reconstruct the shortest path
        path = [destination]
        pred = predecessors[destination]
        while pred != -1:
            path.insert(0, pred)
            try:
                pred = predecessors[pred]
            except IndexError:
                break

        return path[1:-1]  # distances[destination]

    def find_nearest_task_location(self, robot_node_id, task_node_ids, matrix_graph):
        """
        Find the index of the nearest task location to the robot's start node
        using shortest path distances along the graph.
        
        Args:
            robot_node_id: The node ID where the robot is located
            task_node_ids: List of node IDs for task locations
            matrix_graph: A CSR matrix representation of the graph
            
        Returns:
            The index of the nearest task location in the task_node_ids list
        """
        self.logger.info(f"Finding nearest task location to robot at node {robot_node_id}")

        if not task_node_ids:
            self.logger.warning("No task locations provided")
            return None

        # Run Dijkstra's algorithm from the robot node to find distances to all nodes
        try:
            distances, _ = dijkstra(
                matrix_graph, indices=robot_node_id, return_predecessors=True)
        except Exception as e:
            self.logger.error(f"Dijkstra algorithm failed: {str(e)}")
            self.logger.error(f"Exception details: {str(e)}", exc_info=True)
            return None

        # Find the task node with the minimum distance
        min_distance = float('inf')
        nearest_index = None

        for i, node_id in enumerate(task_node_ids):
            if node_id >= len(distances):
                self.logger.warning(f"Task node {node_id} is out of bounds")
                continue

            distance = distances[node_id]
            self.logger.info(f"Graph distance to task {i} at node {node_id}: {distance:.2f}")

            if distance < min_distance:
                min_distance = distance
                nearest_index = i

        if nearest_index is None:
            self.logger.warning("No reachable task locations found")
            return None

        self.logger.info(
            f"Nearest task is at index {nearest_index} (node {task_node_ids[nearest_index]}) with distance {min_distance:.2f}")

        return nearest_index

    def optimize_graph_cpu(self, robots: list[RobotObjectV1], task: Task, graph: WaypointGraph):
        """
        This is a CPU based implementation of Dijkstra to derive a deterministic path
        This will only work for one given robot at a time, and is slow
        """

        # TODO Determine closest robot to the initial node of the task
        # Just use the first available robot until then
        start_node = self.robots.get_robot_location(robots[0].name)

        # Calculate shape
        n = len(graph.offsets) - 1

        # Create a CSR matrix
        matrix_graph = csr_matrix(
            (graph.weights, graph.edges, graph.offsets), shape=(n, n))

        assembled_route = []
        assembled_types = []
        assembled_task_id = ["Depot"]
        at_depot = True
        for node in task.task_locations:
            route = self.shortest_path(matrix_graph, start_node, node)
            if not route:
                raise ValueError("Unreachable node in route optimization")

            self.logger.debug("Shortest path from %d to %d is %s",
                              start_node, node, route)
            assembled_route.extend(route)
            if at_depot is True:
                assembled_types.extend(["Depot"])
                at_depot = False
            else:
                assembled_types.extend(["Delivery"])
            assembled_types.extend(["w"] * (len(route) - 1))
            start_node = node
        assembled_route.append(start_node)
        assembled_types.append("Delivery")

        # This is not exact the same as the cuopt return data structure, but it's a start
        start_node_index = self.find_nearest_task_location(
            self.robots.get_robot_location(robots[0].name), task.task_locations, matrix_graph)
        assembled_task_id.extend([start_node_index])

        # Here we need to emulate the cuopt return data structure:
        ret_struct: dict = {}
        ret_struct.setdefault("vehicle_data", {}).setdefault(
            robots[0].name, {})["route"] = assembled_route
        ret_struct.setdefault("vehicle_data", {}).setdefault(
            robots[0].name, {})["type"] = assembled_types
        ret_struct.setdefault("vehicle_data", {}).setdefault(
            robots[0].name, {})["task_id"] = assembled_task_id

        return ret_struct

    async def get_available_objects(self, robot: RobotObjectV1):
        """ Get available objects pertaining to selected robot """
        self.logger.debug("Getting available objects")
        # Robots from database are returned as dicts
        db_robot = await self.mission_database_client.get_robot(robot.name)
        if not db_robot:
            raise ValueError(f"No robot named {robot.name}")
        if not db_robot.status.online:
            raise ValueError(f"Robot {robot.name} is not online")

        submission = await self.mission_dispatch_client.get_available_objects(
            robot.name)

        self.logger.info(
            "Waiting for available objects to be retrieved from client.")

        mission_name = submission["name"]
        mission_completed = await self.wait_for_mission(mission_name)
        if not mission_completed:
            self.logger.error("Object detection error")
            raise ICSServerError("Object detection mission failed.")

        detector = await self.mission_database_client.get_detection_results(
            robot.name)

        return detector.status.detected_objects

    # Change to use watch API?
    async def wait_for_mission(self, mission_name: str) -> bool:
        """ Given mission name, returns True if mission completes successfully, else False"""
        mission = await self.mission_database_client.get_mission(mission_name)
        while not mission.status.state.done:
            mission = await self.mission_database_client.get_mission(mission_name)
            await asyncio.sleep(1)
        return mission.status.state == MissionStateV1.COMPLETED

    async def wait_for_mission_wrapper(self, mission_name: str, index: int) -> tuple[bool, int]:
        """Calls wait_for_mission but also returns index"""
        result = await self.wait_for_mission(mission_name)
        return result, index

    async def health(self) -> bool:
        return self.initialized

    async def _get_route_path_data(self, mission_data: MissionData, robots=None) -> RouteVisualizationData:
        """
        Generate route path data using either Dijkstra or cuOpt.
        
        Args:
            mission_data: The MissionData object containing route information
            robots: Optional list of robots to use for cuOpt (if None, will use first available robot)
            
        Returns:
            RouteVisualizationData: Route path data including detailed path, waypoints, and metadata
        """
        self.logger.info(f"Generating route path data using {mission_data.solver}")
        
        # Try to use the common route calculation logic
        try:
            # For visualization, we don't need mandatory robots
            mandatory_robot = None
            if robots:
                mandatory_robot = robots[0]
            
            ret_val, msg, _, assembled_mission = await self._calculate_route(
                mission_data, mandatory_robot)
            
            if not ret_val:
                self.logger.error("Route calculation failed")
                raise ICSServerError(f"Route optimization failed: {msg}")
            
            # Get the node coordinates from the WPG cache
            node_locations = self.wpg_cache.nodes
            
            # Extract the route path based on solver type
            route_path = []
            
            # Extract the robot name directly from the message
            robot_name = list(msg["vehicle_data"].keys())[0]
            route_nodes = msg["vehicle_data"][robot_name]["route"]
            
            # Convert route nodes to path points
            for node in route_nodes:
                node_data = node_locations[node]
                route_path.append(Point(
                    x=node_data["x"],
                    y=node_data["y"],
                    z=0
                ))
            
            # Create and return the visualization data
            return RouteVisualizationData(
                waypoints=assembled_mission.points,
                route_path=route_path,
                metadata={
                    "map_id": self.wpg_cache.map_id,
                    "routing_solver": mission_data.solver.value if mission_data.solver else SolverType.CPU_DIJKSTRA.value
                }
            )
        except Exception as e:
            self.logger.error(f"Error generating route path data: {str(e)}")
            raise ICSServerError(f"Failed to generate route visualization: {str(e)}") from e

    async def visualize_route(self, mission_data: MissionData):
        """
        Create a visualization of the route without actually submitting a mission.
        Returns an image with the route drawn on the map.
        
        Args:
            mission_data: The MissionData object containing route information
            
        Returns:
            bytes: PNG image with the route visualized on the map
        """
        self.logger.info("Generating route visualization image")
        
        # First, get the route visualization data
        viz_data = await self._get_route_path_data(mission_data)
        
        # Get the map image from the graph cache
        map_id = self.wpg_cache.map_id
        response = self.wpg_client.get_visualization(map_id)
        
        if response.status_code != 200:
            self.logger.error(f"Failed to get map visualization: {response.status_code}")
            raise ICSServerError("Failed to get map visualization from WPG")
        
        # Load the image and prepare for drawing
        
        img = Image.open(io.BytesIO(response.content))
        draw = ImageDraw.Draw(img)
        
        # Get map metadata to convert world coordinates to pixel coordinates
        map_config = self.config.get_map_config()
        resolution = map_config.metadata.resolution
        origin_x = map_config.metadata.x_offset
        origin_y = map_config.metadata.y_offset
        
        # Function to convert world coordinates to pixel coordinates
        def world_to_pixel(x, y):
            # Convert from world coordinates to pixel coordinates
            # The Y-axis is inverted in the image compared to world coordinates
            pixel_x = int((x - origin_x) / resolution)
            pixel_y = int(img.height - ((y - origin_y) / resolution))
            return pixel_x, pixel_y
        
        # Draw the route path
        path_points = []
        for point in viz_data.route_path:
            px, py = world_to_pixel(point.x, point.y)
            path_points.append((px, py))
        
        # Draw the path lines
        if len(path_points) > 1:
            draw.line(path_points, fill=(0, 255, 0), width=4)  # Green line
        
        # Draw waypoints
        waypoint_radius = 5
        for i, point in enumerate(viz_data.waypoints):
            px, py = world_to_pixel(point.x, point.y)
            color = (255, 0, 0)  # Red
            # Draw a filled circle for each waypoint
            draw.ellipse([(px-waypoint_radius, py-waypoint_radius), 
                           (px+waypoint_radius, py+waypoint_radius)], 
                          fill=color)
            
            # Add a number label next to the waypoint
            draw.text((px + waypoint_radius + 2, py - waypoint_radius - 2), 
                       str(i), fill=(0, 0, 0))
        
        # Add solver type as text on the image
        solver_text = f"Solver: {viz_data.metadata['routing_solver']}"
        draw.text((10, 10), solver_text, fill=(0, 0, 0))
        
        # Convert the image to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # Optionally save the image if configured
        if map_config.save_route_visualization:
            os.makedirs(map_config.route_visualization_path, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{map_config.route_visualization_path}/route_{timestamp}.png"
            img.save(filename)
            self.logger.info(f"Saved route visualization to {filename}")
        
        return img_byte_arr.getvalue()

    async def register_sap_robots(self, sap_service=None):
        """
        Register robots from SAP EWM System
        
        Args:
            sap_service: Optional SapEwmService instance. If None, a new one will be created.
            
        Returns:
            Number of newly registered robots
        """
        try:
            # Create SAP service if not provided
            if sap_service is None:
                import httpx
                import ssl
                
                # Create a client with SSL verification disabled
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                temp_client = httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(
                        retries=3,
                        verify=False  # Disable SSL verification
                    ),
                    timeout=60.0
                )
                
                from app.api.clients.sap_ewm_client import SapEwmService
                sap_config = self.config.get_sap_config()
                sap_service = SapEwmService(temp_client, sap_config)
            
            # Get SAP resources (robots)
            resources = await sap_service.get_warehouse_resources()
            self.logger.info(f"Found {len(resources)} SAP resources (robots)")
            
            # Create list of robot objects
            sap_robots = []
            for resource in resources:
                robot_name = resource["EWMResource"]
                # Create a robot object with data from the SAP resource
                robot_obj = RobotObjectV1(
                    name=robot_name,
                    labels=[resource["EWMResourceGroup"], resource["EWMResourceType"]],
                    heartbeat_timeout=30,
                    status={
                        "online": True,
                        "pose": {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                            "orientation": {
                                "x": 0.0,
                                "y": 0.0, 
                                "z": 0.0,
                                "w": 1.0
                            }
                        },
                        "battery": {
                            "percentage": 100.0,
                            "charging": False
                        }
                    }
                )
                sap_robots.append(robot_obj)
            
            # Register all SAP robots
            new_robots = await self.mission_database_client.create_robots_if_new(sap_robots)
            return len([r for r in new_robots if r is not None])  # Count non-None results
        except Exception as e:
            self.logger.error(f"Failed to register SAP robots: {str(e)}")
            return 0
