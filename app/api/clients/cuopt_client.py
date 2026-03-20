# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import json
import logging
import time
import pydantic.v1 as pydantic
from httpx import HTTPError
from typing import Optional

from app.api.clients.base_api_client import BaseAPIClient
from app.api.clients.cuopt_service_client import CuOptServiceClient
from app.core.task import Task
from app.common.waypoint_graph import WaypointGraph
from cloud_common.objects.robot import RobotObjectV1


class CuOptOptimizationException(Exception):
    """ CuOpt error exception """
    pass


class CuOptFleetData(pydantic.BaseModel):
    """ CuOpt Fleet representation """
    vehicle_locations: list
    vehicle_ids: list
    drop_return_trips: list
    capacities: Optional[list] = None

    def __repr__(self) -> str:
        return str(self.dict())


class CuOptParams(pydantic.BaseModel):
    """ Parameters & defaults to use """
    time_limit: float = .05
    verbose_mode: bool = False


class CuOptSyncObject(pydantic.BaseModel):
    """ _sync object to be passed to CuOpt get_optimized_routes_sync """
    cost_waypoint_graph_data: dict = pydantic.Field("Waypoint Graph")
    task_data: dict = pydantic.Field("Task/job/pick-up/delivery data")
    fleet_data: CuOptFleetData = pydantic.Field("Fleet/techs/robots data.")
    travel_time_matrix_data: dict = pydantic.Field("Cost matrix for time")
    cost_matrix_data: dict = pydantic.Field(
        "Cost of travel from one location to another")
    travel_time_waypoint_graph_data: dict = pydantic.Field(
        "Travel time way point graph")
    solver_config: CuOptParams = pydantic.Field(
        "Solver configuration parameters")

    def __repr__(self) -> str:
        return str(self.dict())


class CuOptClient(BaseAPIClient):
    """ Client for cuOpt API """
    _endpoints: dict = {
        "request": {
            "path": "/cuopt/request",
        },
        "solution": {
            "path": "/cuopt/solution",
        }
    }
    _solver_timeout: int = 30

    async def optimize_graph(self, robots: list[RobotObjectV1], robot_locations: list[int],
                             task: Task, graph: WaypointGraph,
                             robot_capacities: Optional[list[int]] = None):
        """ Main workflow method
        Receives a mission map and calls the cuOpt API to set the graph, task and robot information.
        Finally gets the optimized route assignments and saves them on the map"""
        try:
            routes = await self.get_optimized_routes_sync(
                robots, robot_locations, task, graph, robot_capacities)
            return True, routes["response"]["solver_response"]
        except (CuOptOptimizationException, KeyError, ValueError) as exc:
            logging.error(
                "Route generation/optimization failed: %s", exc.args[0])
            return False, exc.args[0]

    async def get_optimized_routes_sync(self, robots: list[RobotObjectV1], robot_locations: list[int],
                                        task: Task, graph: WaypointGraph,
                                        robot_capacities: Optional[list[int]] = None):
        """ Gets and returns the optimized routes from cuOpt"""
        cost_waypoint_graph_data = {
            "waypoint_graph": {
                # Provide a CSR graph representation of the waypoint graph
                "0": graph.get_graph_edges_offsets_weights()
            }
        }
        logging.debug("Graph data:")
        logging.debug(cost_waypoint_graph_data)

        task_data = task.get_task_data()
        logging.debug("task_data:")
        logging.debug(task_data)
        if len(task_data) == 0:
            raise CuOptOptimizationException(
                "Task data missing, all fields are empty.")

        if len(robots) == 0:
            raise CuOptOptimizationException("No robots found")

        fleet_data = CuOptFleetData(
            vehicle_locations=[
                [node_id, node_id] for node_id in robot_locations
            ],
            vehicle_ids=[
                robot.name for robot in robots
            ],
            # Should we return to origin or drop the return trip
            drop_return_trips=[True] * len(robots)
        )
        if robot_capacities:
            fleet_data.capacities = [robot_capacities]

        # Construct the solve structure
        params = CuOptParams(**self._config["solve_parameters"])
        sync_object = CuOptSyncObject(cost_waypoint_graph_data=cost_waypoint_graph_data,
                                      task_data=task_data,
                                      fleet_data=fleet_data,
                                      travel_time_matrix_data={},
                                      cost_matrix_data={},
                                      travel_time_waypoint_graph_data={},
                                      solver_config=params)
        logging.debug(json.dumps(sync_object.dict()))
        logger = logging.getLogger("Isaac Mission Control")
        try:
            endpoint = self._base_url + \
                self._endpoints["request"]["path"]
            logger.debug("USING SELF HOSTED CUOPT")
            request_id_response = await self.make_request_with_logs("post", endpoint,
                                                            "Failed to obtain cuOpt request_id",
                                                            "cuOpt request_id obtained",
                                                            json=sync_object.dict())
            reqId = request_id_response["reqId"]
            endpoint = self._base_url + \
                self._endpoints["solution"]["path"] + \
                "/" + reqId
            # Poll for the request to complete
            start_time = time.time()
            while time.time() - start_time < self._solver_timeout:
                logger.debug("Polling cuOpt request id %s...", reqId)
                try:
                    cuopt_status_response = await self.make_request_with_logs(
                        "get",
                        endpoint,
                        "cuOpt solver error",
                        "cuOpt optimized routes obtained",
                        suppress_msg=True,
                    )
                    logger.debug("cuOpt status response: %s", cuopt_status_response)

                    # Successful solver response available
                    if (
                        cuopt_status_response
                        and "response" in cuopt_status_response
                        and "solver_response" in cuopt_status_response["response"]
                    ):
                        return cuopt_status_response
                except HTTPError as err:
                    # Connection may not be ready yet; log and retry until timeout
                    logger.debug("cuOpt polling attempt failed: %s", err)
                except Exception as err:
                    # Any other error: log and retry
                    logger.debug("cuOpt polling exception: %s", err)

                await asyncio.sleep(0.5)

            raise CuOptOptimizationException(
                f"cuOpt solver timeout after {self._solver_timeout} seconds"
            )
        except HTTPError as exc:
            # Catch httpx network and protocol errors so that Mission Control can
            # gracefully fall back to the CPU-based solver when the cuOpt service
            # is unavailable.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 409:
                raise CuOptOptimizationException(
                    "cuOpt solver error: HTTP 409 : Failed to find solution") from exc
            else:  # General unknown cuOpt failure
                raise CuOptOptimizationException(
                    f"Unknown cuOpt HTTPError (status_code={status_code}): {exc}") from exc
