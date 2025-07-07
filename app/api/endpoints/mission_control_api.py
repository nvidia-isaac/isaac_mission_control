# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import uuid
import logging
from typing import Optional, Union
from fastapi import FastAPI, HTTPException, status, Response
from pydantic import ValidationError
from app.core.mission_control import MissionControl
from app.core.objectives import ObjectiveExecutor
from app.api.clients.cuopt_client import CuOptOptimizationException
from app.common.models import MissionData, PickPlaceData
from cloud_common.objects.common import ICSError, ICSServerError
from cloud_common.objects.objective import ObjectiveBehaviorNode, ObjectiveCompositeNode, ObjectiveDecoratorNode
from app.api.endpoints.sap_api import router as sap_router


app = FastAPI(
    title="Mission Control API",
    openapi_tags=[
        {
            "name": "Main",
            "description": "Main mission control and robot operations endpoints"
        },
        {
            "name": "SAP",
            "description": "SAP integration endpoints for warehouse management operations"
        }
    ]
)
logger = logging.getLogger("Isaac Mission Control")

async def mc_ready():
    """ If MC is initialized, return MC, else raise 503"""
    try:
        mc = MissionControl.get_instance()
        mc_healthy = await mc.health()
        if mc_healthy:
            return mc
        else:
            raise ICSServerError("Mission Control is not available.")
    except ICSServerError as exc:
        raise HTTPException(status_code=503, detail=exc.args[0]) from exc


@app.post("/mission/submit_mission", tags=["Main"])
@app.post("/mission/submitMission", include_in_schema=False)
async def mission_submit(mission: MissionData, mission_id: Optional[str] = None,
                         mandatory_robot_name: Optional[str] = None):
    """ Create a new mission and execute it """
    try:
        mc = await mc_ready()
        robot = None
        if not mission_id:
            mission_id = str(uuid.uuid4())
        if mandatory_robot_name:
            robot_inventory = mc.robots
            robot = robot_inventory.get_robot(mandatory_robot_name)
        return await mc.submit_navigation_mission(mission_id,
                                                  mission,
                                                  robot)
    except (ValidationError, ValueError, KeyError, CuOptOptimizationException, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/charging", tags=["Main"])
async def send_charging_mission(robot_name: str, dock_id: Optional[str] = None):
    """ Send charging mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        mission_id = uuid.uuid4()
        return await mc.submit_charging_mission(mission_id, robot, dock_id)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.get("/mission/get_available_objects", tags=["Main"])
async def get_available_objects(robot_name: str):
    """ Get the available objects from camera """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.get_available_objects(robot)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/undock", tags=["Main"])
async def send_undock_mission(robot_name: str):
    """ Send undocking mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.submit_undock_mission(robot)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/pick_and_place", tags=["Main"])
async def send_pickplace_mission(robot_name: str, pick_place_data: PickPlaceData):
    """ Send pick and place mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        mission_id = uuid.uuid4()
        return await mc.submit_pickplace_mission(mission_id, robot, pick_place_data)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Main"])
@app.post("/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def mission_control_healthcheck():
    """ Check if service is healthy """
    await mc_ready()
    return {"status": "Mission Control: Running"}


@app.post("/nvcf", include_in_schema=False)
async def nvcf_endpoint(request_body: dict):
    """Single endpoint for NVCF deployment"""
    if "endpoint" not in request_body:
        raise HTTPException(status_code=400, detail="endpoint field is required")
    if "data" not in request_body:
        raise HTTPException(status_code=400, detail="data field is required")
    endpoint = request_body["endpoint"]
    data = request_body["data"]
    mission_database_client = MissionControl.get_instance().mission_database_client
    logger.debug("Using NVCF endpoint")
    if endpoint == "submit_mission":
        if "mission_data" not in data:
            raise HTTPException(status_code=400, detail="mission_data is required")
        mission_data = MissionData(**data["mission_data"])
        mandatory_robot_name = data.get("mandatory_robot_name", None)
        rst = await mission_submit(mission=mission_data, mandatory_robot_name=mandatory_robot_name)
        return rst
    elif endpoint == "get_robot":
        if not "name" not in data:
            raise HTTPException(status_code=400, detail="name is required")
        robot_obj = await mission_database_client.get_robot(data["name"])
        return robot_obj.dict()
    elif endpoint == "get_robots":
        robot_list = await mission_database_client.get_robots()
        return [robot_obj.dict() for robot_obj in robot_list]
    elif endpoint == "get_mission":
        if not "name" not in data:
            raise HTTPException(status_code=400, detail="name is required")
        mission_obj = await mission_database_client.get_mission(data["name"])
        return mission_obj.dict()
    elif endpoint == "get_missions":
        mission_list = await mission_database_client.get_missions()
        return [mission_obj.dict() for mission_obj in mission_list]
    else:
        return f"Endpoint {endpoint} not found"


@app.post("/visualize_route", response_class=Response, tags=["Main"])
async def visualize_route(mission_data: MissionData):
    """
    Visualize a route without submitting an actual mission.
    Returns an image with the route drawn on the map.

    Args:
        mission_data: The mission data containing the route to visualize

    Returns:
        PNG image with the route visualized on the map
    """
    try:
        mc = await mc_ready()
        image_bytes = await mc.visualize_route(mission_data)
        return Response(content=image_bytes, media_type="image/png")
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


async def submit_objective(data: Union[ObjectiveCompositeNode,
                                       ObjectiveBehaviorNode,
                                       ObjectiveDecoratorNode]):
    """ Submit an objective """
    mc = await mc_ready()
    logging.info(data.dict())
    obj = await mc.mission_database_client.create_objective()
    obj.status.objective_tree = data
    await mc.mission_database_client.update_objective(obj)
    ObjectiveExecutor.get_instance().run_objective(obj)
    return obj.name

async def cancel_objective(objective_name: str):
    """ Cancel an objective """
    mc = await mc_ready()
    obj = await mc.mission_database_client.get_objective(objective_name)
    ObjectiveExecutor.get_instance().cancel_objective(obj)


# Include SAP router
app.include_router(sap_router)


def get_mission_control_app(experimental: bool = False):
    """ App itself """
    if experimental:
        app.add_api_route("/submit_objective", submit_objective, methods=["POST"])
        app.add_api_route("/cancel_objective", cancel_objective, methods=["POST"])
    return app
