# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging
import uuid
import ssl
import httpx
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import ValidationError

from app.core.mission_control import MissionControl
from app.common.models import MissionData, Point, WarehouseOrderStatus
from app.api.clients.sap_ewm_client import SapEwmService

logger = logging.getLogger("Isaac Mission Control")
router = APIRouter(prefix="/sap", tags=["SAP"])


def get_sap_service(request: Request):
    """Get a configured SAP EWM service instance."""
    try:
        # Get SAP configuration
        config = MissionControl.get_instance().config
        sap_config = config.get_sap_config()

        # Create a more flexible SSL context that's less strict for self-signed certs
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Create client with SSL verification disabled via context
        client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(
                retries=3,
                verify=False
            ),
            timeout=60.0
        )
        return SapEwmService(client, sap_config)
    except Exception as e:
        logger.error(f"Error creating SAP service: {e}")
        raise HTTPException(status_code=500, detail=f"SAP EWM service unavailable: {str(e)}")


@router.get("/health")
async def sap_health_check(sap_service: SapEwmService = Depends(get_sap_service)):
    """Check if SAP connection is healthy"""
    try:
        resources = await sap_service.get_warehouse_resources()
        return {
            "status": "ok",
            "message": f"Successfully connected to SAP. Found {len(resources)} resources."
        }
    except Exception as e:
        logger.error(f"SAP health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"SAP connection failed: {str(e)}")


@router.get("/storage-bins", response_model=List[Dict[str, Any]])
async def get_storage_bins(
    bin_name: Optional[str] = None,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Get available storage bins with coordinates."""
    try:
        return await sap_service.get_storage_bins(bin_name)
    except Exception as e:
        logger.error(f"Error fetching storage bins: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources", response_model=List[Dict[str, Any]])
async def get_resources(sap_service: SapEwmService = Depends(get_sap_service)):
    """Get available warehouse resources (robots)."""
    try:
        return await sap_service.get_warehouse_resources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders", response_model=List[Dict[str, Any]])
async def get_orders(
    status: WarehouseOrderStatus = WarehouseOrderStatus.OPEN,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Get warehouse orders with specified status."""
    try:
        return await sap_service.get_warehouse_orders(status.value)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_number}/tasks", response_model=List[Dict[str, Any]])
async def get_tasks_for_order(
    order_number: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Get tasks for a specific warehouse order."""
    try:
        return await sap_service.get_warehouse_tasks_for_order(order_number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_number}/tasks/{task_number}/mission", response_model=Dict[str, Any])
async def get_mission_for_task(
    order_number: str,
    task_number: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Convert a warehouse task to a navigation mission."""
    try:
        tasks = await sap_service.get_warehouse_tasks_for_order(order_number)
        task = next((t for t in tasks if t["WarehouseTask"] == task_number), None)

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        mission = await sap_service.create_navigation_mission_from_task(task)
        return mission
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_number}/tasks/{task_number}/submit-mission", response_model=Dict[str, Any])
async def submit_mission_from_task(
    order_number: str,
    task_number: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Convert a warehouse task to a navigation mission and submit it to Mission Control."""
    try:
        mc = MissionControl.get_instance()

        # Register any new SAP robots
        new_robots_count = await mc.register_sap_robots(sap_service)
        if new_robots_count > 0:
            logger.info(
                f"Registered {new_robots_count} new robots from SAP during mission submission")

        # Get the task
        tasks = await sap_service.get_warehouse_tasks_for_order(order_number)
        logger.info(f"Found {len(tasks)} tasks for order {order_number}")

        task = next((t for t in tasks if t["WarehouseTask"] == task_number), None)
        if not task:
            logger.error(f"Task {task_number} not found in order {order_number}")
            raise HTTPException(status_code=404, detail="Task not found")

        # Create a mission from the task
        sap_mission = await sap_service.create_navigation_mission_from_task(task)

        # Convert sap_mission to MissionData
        mission_data = MissionData(
            route=[Point(x=point["x"], y=point["y"], z=point.get("z", 0))
                   for point in sap_mission.get("route", [])]
        )

        # Submit mission
        result = await mc.submit_navigation_mission(str(uuid.uuid4()), mission_data)

        return {
            "mission": sap_mission,
            "mission_control_result": result
        }
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Mission data validation error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting mission: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_number}/{task_item}/confirm", response_model=Dict[str, Any])
async def confirm_task(
    task_number: str,
    task_item: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Confirm task completion."""
    try:
        logging.debug(f"Confirming task {task_number}/{task_item}")
        return await sap_service.confirm_warehouse_task(task_number, task_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_number}/assign-robot/{robot_name}", response_model=Dict[str, Any])
async def assign_robot_to_order(
    order_number: str,
    robot_name: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Assign a specific robot to a warehouse order in SAP EWM."""
    try:
        # Verify the order exists
        orders = await sap_service.get_warehouse_orders()
        order = next((o for o in orders if o["WarehouseOrder"] == order_number), None)
        if not order:
            logger.error(f"Order {order_number} not found")
            raise HTTPException(status_code=404, detail="Order not found")

        # Verify the robot exists
        resources = await sap_service.get_warehouse_resources()
        robot = next((r for r in resources if r["EWMResource"] == robot_name), None)
        if not robot:
            logger.error(f"Robot resource {robot_name} not found")
            raise HTTPException(status_code=404, detail="Robot resource not found")

        # First, log on to the resource
        try:
            logon_result = await sap_service.logon_to_resource(robot_name)
            logger.info(f"Successfully logged on to resource {robot_name}")
        except ValueError as e:
            logger.warning(f"Resource logon warning: {e}")
            # Continue even if logon fails, as it might already be logged on

        # Unassign any previous resource from the order
        try:
            unassign_result = await sap_service.unassign_warehouse_order(order_number)
            logger.info(f"Successfully unassigned previous resources from order {order_number}")
        except Exception as e:
            logger.warning(f"Unassign warning: {e}")
            # Continue even if unassign fails

        # Now assign the robot to the order
        result = await sap_service.assign_robot_to_warehouse_order(order_number, robot_name)

        # Update the local tracking in the background task system
        mc = MissionControl.get_instance()
        if hasattr(mc, 'sap_background_task') and mc.sap_background_task:
            mc.sap_background_task.order_robot_assignments[order_number] = robot_name
            logger.info(
                f"Updated local tracking for order {order_number} assignment to robot {robot_name}")

        return {
            "order_number": order_number,
            "robot_name": robot_name,
            "status": "assigned",
            "result": result
        }
    except ValueError as e:
        logger.error(f"Error in robot assignment: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error assigning robot to order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resources/{resource_name}/logon", response_model=Dict[str, Any])
async def logon_to_resource(
    resource_name: str,
    sap_service: SapEwmService = Depends(get_sap_service)
):
    """Log on to a warehouse resource in SAP EWM."""
    try:
        # Verify the robot exists
        resources = await sap_service.get_warehouse_resources()
        robot = next((r for r in resources if r["EWMResource"] == resource_name), None)
        if not robot:
            logger.error(f"Robot resource {resource_name} not found")
            raise HTTPException(status_code=404, detail="Robot resource not found")

        # Log on to the resource
        result = await sap_service.logon_to_resource(resource_name)

        return {
            "resource_name": resource_name,
            "status": "logged_on",
            "result": result
        }
    except ValueError as e:
        logger.error(f"Error in resource logon: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error logging on to resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))
