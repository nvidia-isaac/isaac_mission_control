# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import io
import uuid
import unittest
import asyncio
import zipfile
import yaml

import httpx
from PIL import Image

from app.tests import test_context
from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.common.models import NVActionType
from cloud_common.objects.robot import RobotStateV1


def _generate_png_bytes(size: int = 64) -> bytes:
    """Generate an in-memory grayscale PNG.

    A simple black square with a white border is sufficient for the
    Waypoint-Graph-Generator to treat it as a valid occupancy grid.
    """
    img = Image.new("L", (size, size), color=0)  # black
    for x in range(size):
        for y in (0, size - 1):
            img.putpixel((x, y), 255)  # white border top/bottom
    for y in range(size):
        for x in (0, size - 1):
            img.putpixel((x, y), 255)  # white border left/right

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_metadata_yaml(image_name: str) -> bytes:
    """Return YAML bytes in a ROS map-metadata schema for *image_name*."""
    yaml_content = (
        f"image: {image_name}\n"
        "resolution: 0.05\n"
        "origin: [0.0, 0.0, 0.0]\n"
        "negate: 0\n"
        "occupied_thresh: 0.65\n"
        "free_thresh: 0.196\n"
        "safety_distance: 0.5\n"
    )
    return yaml_content.encode()


class TestMapUpdate(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests for Mission Control map management endpoints."""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=120.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_upload_list_preview_select(self):
        """Validate the complete happy-path for uploading and activating a new map."""

        async with test_context.TestContext(async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client
            )

            mc_online = await mission_control_client.wait_for_mc_alive()
            self.assertTrue(mc_online)

            # --- 1) Upload ------------------------------------------------------------------
            map_id = f"testmap_{uuid.uuid4().hex}"
            image_filename = f"{map_id}.png"

            upload_payload = await mission_control_client.upload_map(
                map_id=map_id,
                image_bytes=_generate_png_bytes(),
                image_filename=image_filename,
                metadata_yaml_bytes=_generate_metadata_yaml(image_filename),
                metadata_filename=f"{map_id}.yaml",
            )
            self.assertTrue(upload_payload["success"])
            self.assertEqual(upload_payload["map_id"], map_id)

            # --- 2) List --------------------------------------------------------------------
            maps = await mission_control_client.list_maps()
            self.assertIn(map_id, maps)

            # --- 3) Preview -----------------------------------------------------------------
            preview_bytes = await mission_control_client.preview_map(map_id)
            self.assertEqual(preview_bytes, _generate_png_bytes())


            # --- 4) Select ------------------------------------------------------------------
            select_payload = await mission_control_client.select_map(map_id)
            self.assertTrue(select_payload["success"])
            self.assertEqual(select_payload["map_id"], image_filename)

            async def _collect_new_missions(ref_names: set[str]) -> list:
                for _ in range(30):
                    missions = await ctx.mission_database_client.get_missions({"most_recent": 30})
                    new = [m for m in missions if m.name not in ref_names]
                    if new:
                        return new
                    await asyncio.sleep(1)
                return []

            # --- 5) Update robot map ---------------------------------------------------------
            # Capture baseline missions *before* triggering the robot update
            existing_missions = await ctx.mission_database_client.get_missions({"most_recent": 30})
            existing_names = {m.name for m in existing_missions}

            upd_payload = await mission_control_client.update_robot_map("robot_a", map_id)
            self.assertTrue(upd_payload["success"])
            self.assertEqual(upd_payload["map_id"], image_filename)
            self.assertEqual(upd_payload["robot"], "robot_a")
            map_download_link = upd_payload["map_download_link"]
            self.assertTrue(map_download_link.endswith(f"/maps/{map_id}.zip"))

            # --- 6) Verify Missions for map actions ----------------------------------------

            new_missions = await _collect_new_missions(existing_names)
            self.assertGreaterEqual(len(
                new_missions), 2, "Expected download & enable missions after update_robot_map")

            found_download = found_enable = False
            for m in new_missions:
                first_node = m.mission_tree[0]
                if first_node.action:
                    atype = first_node.action.action_type
                    if atype == NVActionType.DOWNLOAD_MAP:
                        found_download = True
                        self.assertEqual(first_node.name, "download_map")
                        self.assertEqual(first_node.action.action_parameters.get(
                            "mapId"), image_filename)
                        self.assertEqual(first_node.action.action_parameters.get(
                            "mapDownloadLink"), map_download_link)
                        self.assertIn("mapHash", first_node.action.action_parameters)
                    elif atype == NVActionType.ENABLE_MAP:
                        found_enable = True
                        self.assertEqual(first_node.name, "enable_map")
                        self.assertEqual(first_node.action.action_parameters.get(
                            "mapId"), image_filename)

            self.assertTrue(
                found_download, "No download_map mission created after update_robot_map")
            self.assertTrue(
                found_enable, "No enable_map mission created after update_robot_map")

    async def test_update_robot_conflict_when_not_idle(self):
        """Robot not IDLE should return 409 when updating map."""
        async with test_context.TestContext(async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client
            )
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client
            )

            mc_online = await mission_control_client.wait_for_mc_alive()
            self.assertTrue(mc_online)

            # Upload a map so it is available for update_robot_map
            map_id = f"busy_map_{uuid.uuid4().hex}"
            image_filename = f"{map_id}.png"
            _ = await mission_control_client.upload_map(
                map_id=map_id,
                image_bytes=_generate_png_bytes(),
                image_filename=image_filename,
                metadata_yaml_bytes=_generate_metadata_yaml(image_filename),
                metadata_filename=f"{map_id}.yaml",
            )

            # Ensure robots are ready on the base map
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            self.assertTrue(robots_online)

            # Start a simple mission on the base map to move robot_a out of IDLE
            mission_req = {
                "mission_id": f"make_busy_{uuid.uuid4().hex}",
                "mission_template": "simple_navigation_mission",
                "mission_data": {"route": [{"x": 8, "y": 8}]},
            }
            _ = await mission_control_client.send_mission(mission_req)

            # Wait until robot_a is not IDLE (or timeout)
            for _ in range(60):
                robot = await mission_database_client.get_robot("robot_a")
                if robot.status.state != RobotStateV1.IDLE:
                    break
                await asyncio.sleep(1)
            else:
                self.fail("Robot did not leave IDLE state in time")

            # Attempt to update map on a non-idle robot should yield 409
            with self.assertRaises(httpx.HTTPStatusError) as err_ctx:
                await mission_control_client.update_robot_map("robot_a", map_id)
            self.assertEqual(getattr(err_ctx.exception.response, "status_code", None), 409)

    async def test_download_link_bundle_contents(self):
        """Verify the map ZIP bundle contains PNG and YAML with corrected YAML image field."""
        async with test_context.TestContext(async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client
            )

            mc_online = await mission_control_client.wait_for_mc_alive()
            self.assertTrue(mc_online)

            # Upload map (PNG + YAML)
            map_id = f"bundle_map_{uuid.uuid4().hex}"
            image_filename = f"{map_id}.png"
            yaml_filename = f"{map_id}.yaml"
            png_bytes = _generate_png_bytes()
            _ = await mission_control_client.upload_map(
                map_id=map_id,
                image_bytes=png_bytes,
                image_filename=image_filename,
                metadata_yaml_bytes=_generate_metadata_yaml(image_filename),
                metadata_filename=yaml_filename,
            )

            # Select uploaded map
            _ = await mission_control_client.select_map(map_id)

            # Trigger update_robot_map to generate the bundle and link
            payload = await mission_control_client.update_robot_map("robot_a", map_id)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["map_id"], image_filename)
            download_link = payload["map_download_link"]
            self.assertTrue(download_link.endswith(f"/maps/{map_id}.zip"))

            # Fetch the ZIP and validate contents
            zip_resp = await self.client.get(download_link)
            self.assertEqual(zip_resp.status_code, 200, zip_resp.text)
            zf = zipfile.ZipFile(io.BytesIO(zip_resp.content), "r")
            names = set(zf.namelist())
            self.assertIn(image_filename, names)
            self.assertIn(yaml_filename, names)

            # PNG bytes should match upload
            zipped_png = zf.read(image_filename)
            self.assertEqual(zipped_png, png_bytes)

            # YAML should have image field corrected to the image filename
            yaml_bytes = zf.read(yaml_filename)
            yaml_data = yaml.safe_load(yaml_bytes.decode("utf-8"))
            self.assertIsInstance(yaml_data, dict)
            self.assertEqual(yaml_data.get("image"), image_filename)

if __name__ == "__main__":
    unittest.main()
