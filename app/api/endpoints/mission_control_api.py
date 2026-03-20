# Copyright (c) 2024-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import uuid
import logging
from typing import Optional, Union
from fastapi import FastAPI, HTTPException, status, Response, UploadFile, File, Request
from pydantic.v1 import ValidationError
from app.core.mission_control import MissionControl
from app.core.objectives.objectives import ObjectiveExecutor
from app.api.clients.cuopt_client import CuOptOptimizationException
from app.common.models import MissionData, PickPlaceData, MultiObjectPickPlaceData
from cloud_common.objects.common import ICSError, ICSServerError
from cloud_common.objects.objective import ObjectiveBehaviorNode, ObjectiveCompositeNode, ObjectiveDecoratorNode
from app.api.endpoints.sap_api import router as sap_router
from app.core.mission_control_config import MapConfig
import os
from fastapi.staticfiles import StaticFiles
import zipfile
import hashlib
from cloud_common.objects.robot import RobotStateV1
import yaml


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
        },
        {
            "name": "Objectives",
            "description": "Objectives endpoints for managing objectives"
        }
    ]
)
logger = logging.getLogger("Isaac Mission Control")


# Directory on disk where uploaded maps are stored
MAP_STORAGE_DIR = os.getenv(
    "MC_MAP_STORAGE_DIR", "/tmp/config/uploaded_maps")
os.makedirs(MAP_STORAGE_DIR, exist_ok=True)

# Expose the raw files so UIs can fetch them directly
app.mount("/maps", StaticFiles(directory=MAP_STORAGE_DIR), name="uploaded_maps")

# Registry of uploaded maps in memory (map_id -> MapConfig)
app.state.available_maps = {}


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
        if mandatory_robot_name:
            robot_inventory = mc.robots
            robot = robot_inventory.get_robot(mandatory_robot_name)
        return await mc.submit_navigation_mission(mission,
                                                  robot,
                                                  mission_id)
    except (ValidationError, ValueError, KeyError, CuOptOptimizationException, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/charging", tags=["Main"])
async def send_charging_mission(robot_name: str, dock_id: Optional[str] = None, mission_id: Optional[str] = None):
    """ Send charging mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.submit_charging_mission(robot, dock_id, mission_id)
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


@app.get("/mission/get_available_apriltags", tags=["Main"])
async def get_available_apriltags(robot_name: str):
    """ Get the available AprilTags from camera """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.get_available_apriltags(robot)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/undock", tags=["Main"])
async def send_undock_mission(robot_name: str, mission_id: Optional[str] = None):
    """ Send undocking mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.submit_undock_mission(robot, mission_id)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/pick_and_place", tags=["Main"])
async def send_pickplace_mission(robot_name: str, pick_place_data: PickPlaceData, mission_id: Optional[str] = None):
    """ Send pick and place mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.submit_pickplace_mission(robot, pick_place_data, mission_id)
    except (ValidationError, ValueError, KeyError, ICSError) as exc:
        logger.error(exc)
        logger.error(exc.args[0])
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@app.post("/mission/multi_object_pickplace", tags=["Main"])
async def send_multi_object_pickplace_mission(robot_name: str, multi_object_pickplace_data: MultiObjectPickPlaceData,
                                              mission_id: Optional[str] = None):
    """ Send multi-object pick and place mission """
    try:
        mc = await mc_ready()
        robot_inventory = mc.robots
        robot = robot_inventory.get_robot(robot_name)
        return await mc.submit_multi_object_pickplace_mission(robot, multi_object_pickplace_data, mission_id)
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

@app.post("/objective/submit_objective", tags=["Objectives"])
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

@app.post("/objective/cancel_objective", tags=["Objectives"])
async def cancel_objective(objective_name: str):
    """ Cancel an objective """
    mc = await mc_ready()
    obj = await mc.mission_database_client.get_objective(objective_name)
    ObjectiveExecutor.get_instance().cancel_objective(obj)


# Include SAP router
app.include_router(sap_router)


def get_mission_control_app():
    """ App itself """
    return app


@app.get("/map", response_class=Response, tags=["Main"])
async def get_current_map():
    """Return the map file configured in Mission Control.

    The binary data of the currently configured map is returned with the
    appropriate MIME type so that clients can directly download it.
    """
    try:
        mc = await mc_ready()
        map_config = mc.config.get_map_config()

        # Retrieve the map bytes and content-type
        map_file_data = map_config.get_map_file()["map_file"]
        filename, file_content, content_type = map_file_data

        # Fall back to generic binary type if no MIME could be determined
        media_type = content_type or "application/octet-stream"
        headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}
        return Response(content=file_content, media_type=media_type, headers=headers)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unable to provide map file: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/map/metadata", tags=["Main"])
async def get_map_metadata():
    """Expose the metadata of the currently loaded map (resolution, offsets …)."""
    try:
        mc = await mc_ready()
        map_config = mc.config.get_map_config()
        if not map_config.metadata:
            raise ValueError("No map metadata configured.")
        return map_config.metadata.dict()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unable to provide map metadata: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/map/upload", tags=["Main"])
async def upload_map(request: Request, map_image: UploadFile = File(...), metadata_yaml: UploadFile | None = File(None), map_id: str | None = None):
    """Upload a map image (and optionally its YAML metadata) to Mission Control.

    """
    # Validate file type (basic check)
    if map_image.filename.split(".")[-1].lower() not in {"png", "jpg", "jpeg"}:
        raise HTTPException(
            status_code=400, detail="Only PNG/JPG images accepted")

    # Determine map_id
    map_id = map_id or os.path.splitext(
        os.path.basename(map_image.filename))[0]

    # Save image
    img_path = os.path.join(
        MAP_STORAGE_DIR, f"{map_id}{os.path.splitext(map_image.filename)[1]}")
    with open(img_path, "wb") as dst:
        dst.write(await map_image.read())

    # Save metadata YAML if provided
    metadata_path = ""
    if metadata_yaml:
        metadata_path = os.path.join(MAP_STORAGE_DIR, f"{map_id}.yaml")
        with open(metadata_path, "wb") as dst:
            dst.write(await metadata_yaml.read())
        # Rewrite YAML 'image' field to point to the newly stored image name (MAP_ID + ext)
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
            if isinstance(yaml_data, dict):
                yaml_data["image"] = os.path.basename(img_path)
                with open(metadata_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(yaml_data, f, sort_keys=False)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to rewrite YAML image field for %s: %s. Check if YAML is accessible and writable. Ensure storage exists.", metadata_path, exc)

    # Build MapConfig referencing the stored file
    cfg_kwargs = {"map_file": img_path}
    if metadata_path:
        cfg_kwargs["metadata_yaml"] = metadata_path

    try:
        uploaded_cfg = MapConfig(**cfg_kwargs)
    except ValueError as exc:
        # Clean up and report error
        os.remove(img_path)
        if metadata_path:
            os.remove(metadata_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Register
    request.app.state.available_maps[map_id] = uploaded_cfg

    return {"success": True, "map_id": map_id}


@app.get("/map/list", tags=["Main"])
async def list_maps(request: Request):
    """Return IDs of maps previously uploaded to Mission Control."""
    return list(request.app.state.available_maps.keys())


@app.get("/map/preview/{map_id}", response_class=Response, tags=["Main"])
async def preview_map(map_id: str, request: Request):
    """Return the image bytes for a map already present in `available_maps`.

    No state mutation – purely read-only. Returns 404 if the ID is unknown.
    """
    cfg: MapConfig | None = request.app.state.available_maps.get(map_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Unknown map_id")

    try:
        file_info = cfg.get_map_contents()
        media_type = file_info["content_type"] or "application/octet-stream"
        return Response(content=file_info["file_content"], media_type=media_type)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to preview map %s: %s", map_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Internal helper performing the actual map-switch procedure.
async def select_map(new_map: MapConfig, request: Optional[Request] = None):
    """Switch Mission Control to *new_map* and regenerate the internal graph.
    """
    mc = await mc_ready()

    # Ensure we have metadata (may come from YAML)
    if new_map.metadata is None:
        new_map.apply_metadata_yaml()
    if new_map.metadata is None:
        raise HTTPException(
            status_code=400, detail="Map metadata missing for selected map")

    # Update config
    mc.config._map_config = new_map

    # Regenerate graph
    await mc.reset_wpg_cache()

    map_id = new_map.metadata.map_id

    return {"success": True, "map_id": map_id}


@app.post("/map/select/{map_id}", tags=["Main"])
async def select_uploaded_map(map_id: str, request: Request):
    """Activate a map that has been uploaded via `/map/upload`."""
    cfg: MapConfig | None = request.app.state.available_maps.get(map_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Unknown map_id")

    return await select_map(cfg, request)


@app.post("/map/update_robot/{robot_name}/{map_id}", tags=["Main"])
async def update_robot_map(robot_name: str, map_id: str, request: Request):
    """Download and enable *map_id* on a specific robot.
    """
    # Verify the requested map exists in the in-memory registry
    cfg: MapConfig | None = request.app.state.available_maps.get(map_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Unknown map_id")

    # Ensure Mission Control is healthy and retrieve the target robot
    mc = await mc_ready()
    try:
        robot = await mc.mission_database_client.get_robot(robot_name)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Robot %s not found: %s", robot_name, exc)
        raise HTTPException(
            status_code=404, detail="Unknown robot_name") from exc
    # Early guard: only allow map-changing when robot is IDLE (return 409 to caller)
    try:
        logger.info(
                "Robot status: %s", robot.status.dict())
        if getattr(robot, "status", None) is None or getattr(robot.status, "state", None) is None:
            logger.warning("Robot %s has no status/state; refusing map update", robot_name)
            raise HTTPException(status_code=409, detail="Robot status unknown. Map update not sent.")
        if robot.status.state != RobotStateV1.IDLE:
            logger.info(
                "Blocking map update for %s: robot state is %s (must be IDLE)",
                robot_name, robot.status.state
            )
            raise HTTPException(
                status_code=409,
                detail=f"Robot not IDLE (state: {robot.status.state}). Map update not sent."
            )
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to validate robot state for %s: %s", robot_name, exc)
        raise HTTPException(status_code=409, detail="Could not validate robot state")

    # Ensure map metadata is available (may be loaded from YAML lazily)
    if cfg.metadata is None:
        cfg.apply_metadata_yaml()
    if cfg.metadata is None:
        raise HTTPException(
            status_code=400, detail="Map metadata missing for selected map")

    # Build ZIP bundle containing image and metadata YAML
    zip_filename = f"{map_id}.zip"
    zip_path = os.path.join(MAP_STORAGE_DIR, zip_filename)

    # Create bundle if it does not exist yet
    if not os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Add image file
            if cfg.map_file and os.path.exists(cfg.map_file):
                zf.write(cfg.map_file, arcname=os.path.basename(cfg.map_file))
            # Add metadata YAML (if local path exists)
            if cfg.metadata_yaml and os.path.exists(cfg.metadata_yaml):
                # Ensure YAML 'image' field matches the bundled image filename
                try:
                    with open(cfg.metadata_yaml, "r", encoding="utf-8") as f:
                        yaml_data = yaml.safe_load(f) or {}
                    if isinstance(yaml_data, dict) and cfg.map_file:
                        desired_image_name = os.path.basename(cfg.map_file)
                        yaml_data["image"] = desired_image_name
                        corrected_yaml = yaml.safe_dump(yaml_data, sort_keys=False)
                        zf.writestr(os.path.basename(cfg.metadata_yaml), corrected_yaml)
                    else:
                        # Fallback to original file if structure unexpected
                        zf.write(cfg.metadata_yaml, arcname=os.path.basename(cfg.metadata_yaml))
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Failed to rewrite YAML in bundle, using original: %s", exc)
                    zf.write(cfg.metadata_yaml, arcname=os.path.basename(cfg.metadata_yaml))

    # Compute SHA256 hash of the bundle for integrity check
    map_hash = ""
    try:
        with open(zip_path, "rb") as fp:
            map_hash = hashlib.sha256(fp.read()).hexdigest()
    except FileNotFoundError:
        logger.warning("Bundle zip not found: %%s", zip_path)

    # Build download link to bundle
    download_link = str(request.url_for("uploaded_maps", path=zip_filename))

    map_id_val = cfg.metadata.map_id

    # Trigger download + enable actions for the single robot
    await mc.mission_dispatch_client.download_map_action(
        [robot],
        map_id=map_id_val,
        map_download_link=download_link,
        map_hash=map_hash,
        timeout_s=600,
    )
    await mc.mission_dispatch_client.enable_map_action(
        [robot],
        map_id=map_id_val,
        timeout_s=600,
    )

    return {"success": True,
            "map_id": map_id_val,
            "robot": robot_name,
            "map_download_link": download_link}
