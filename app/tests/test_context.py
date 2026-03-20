# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, NamedTuple, Optional, Union

from requests import HTTPError

from app.api.clients.cuopt_client import CuOptClient
from app.core.mission_control_config import MissionControlConfig
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.api.clients.mission_dispatch_client import MissionDispatchClient
from app.api.clients.waypoint_graph_generator_client import WaypointGraphGeneratorClient
from app.tests import test_utils
from cloud_common import objects
from cloud_common.objects.robot import VDA5050AgvClass
from cloud_common.objects.objective import ObjectiveCompositeNode, ObjectiveBehaviorNode, ObjectiveDecoratorNode
import httpx
import asyncio
import yaml
import uuid
import atexit
from enum import Enum

# The TCP port for the api server to listen on
DATABASE_PORT = 5002
# The TCP port for the api server to listen for controller traffic
DATABASE_CONTROLLER_PORT = 5003
# The TCP port for the MQTT broker to listen on
MQTT_PORT_TCP = 1885
# The WEBSOCKET port for the MQTT broker to listen on
MQTT_PORT_WEBSOCKET = 9001
# The transport mechanism("websockets", "tcp") for MQTT
MQTT_TRANSPORT = "websockets"
# The path for the websocket if "mqtt_transport" is "websockets""
MQTT_WS_PATH = "/mqtt"
# The port for the MQTT broker to listen on
MQTT_PORT = MQTT_PORT_TCP if MQTT_TRANSPORT == "tcp" else MQTT_PORT_WEBSOCKET
# How far the simulator should move the robots each second
SIM_SPEED = 10
# Starting PostgreSQL Db on this port
POSTGRES_PORT = 5432
# The MQTT topic prefix
MQTT_PREFIX = "uagv/v1"
# Waypoint graph generator port
WPG_PORT = 8000
# Cuopt port
CUOPT_PORT = 5050
# Mission control port
MC_PORT = 8050

# Resolve TEST_BASE symlink to get actual directory for Docker mounts
TEST_BASE = os.path.realpath(os.path.join(os.environ.get("RUNFILES_DIR", ""), os.environ.get("TEST_WORKSPACE", ""), "app/config/test_base.yaml"))
CONFIG_DIR = os.path.dirname(TEST_BASE)  # Actual path to app/config
WORKSPACE = os.path.dirname(os.path.dirname(CONFIG_DIR))  # Actual workspace root (2 levels up from config)
TEMP_CONFIG_DIR = os.path.join(WORKSPACE, ".test_tmp")
os.makedirs(TEMP_CONFIG_DIR, exist_ok=True)
logging.debug("CONFIG_DIR: %s", CONFIG_DIR)


class TestConfigKey(Enum):
    DOCKS = "docks"
    GALILEO_HUBBLE = "galileo_hubble"
    MAP_FILE_SEMANTIC = "map_file_semantic"
    MAP_FILE_SEMANTIC_WITH_DOCK = "map_file_semantic_with_dock"
    MAP_FILE_S3 = "map_file_s3"
    ROBOTS = "robots"
    REPLAN = "replan"
    PICKPLACE = "pickplace"


class RobotInit:
    """Represents the initial state of a robot in the simulation"""

    def __init__(self, name: str, x: float, y: float, theta: float = 0.0, map_id: str = "map",
                 failure_period: int = 0, battery: float = 20.0,
                 manufacturer: str = "RobotCompany", serial_number: str = "",
                 fail_as_warning=False,
                 robot_type: VDA5050AgvClass = VDA5050AgvClass.CARRIER):
        self.name = name
        self.x = x
        self.y = y
        self.theta = theta
        self.map_id = map_id
        self.failure_period = failure_period
        self.battery = battery
        self.manufacturer = manufacturer
        self.serial_number = serial_number or name
        self.fail_as_warning = fail_as_warning
        self.robot_type = robot_type.value

    def __str__(self) -> str:
        params = [self.name, self.x, self.y, self.theta, self.map_id,
                  self.failure_period, self.battery, self.manufacturer,
                  self.serial_number, self.robot_type]
        return ",".join(str(p) for p in params if p is not None)


class Delay(NamedTuple):
    """  Delay to launch """
    mqtt_broker: int = 0
    mission_dispatch: int = 0
    mission_database: int = 0
    mission_simulator: int = 0
    waypoint_graph_generator: int = 0
    postgres: int = 5


class TestContext:
    """Mission control text context"""
    crashed_process = False

    def __init__(self, async_client: httpx.AsyncClient, name="test context",
                 config_file=None,
                 config_overrides=None,
                 delay: Delay = Delay(),
                 robots: Optional[list[RobotInit]] = None):
        print("Starting test context", flush=True)
        self._name = name
        self.processes = []
        self.containers = []
        if TestContext.crashed_process:
            raise ValueError("Can't run test due to previous failure")

        try:
            # If a specific config file is provided, use it instead
            if config_file is None:
                config_file = "/config/test_base.yaml"

            self.config = MissionControlConfig(
                "app" + config_file, config_overrides=config_overrides)

            self._robots = robots if robots else []
            # This data has to be valid on the map specified in the config file
            robot_names = [robot.name for robot in self._robots]
            if "robot_a" not in robot_names:
                self._robots.append(RobotInit("robot_a", 25, 25, battery=100))

            # Register signal handler
            signal.signal(signal.SIGUSR1, self.catch_signal)
            signal.signal(signal.SIGTERM, self.cleanup)

            # Start the Mosquitto broker
            print("Starting mosquitto broker", flush=True)
            self._mqtt_process, self._mqtt_address = self.run_docker(
                "//app/tests/test_utils:mosquitto-img-bundle",
                args=[str(MQTT_PORT_TCP), str(MQTT_PORT_WEBSOCKET)],
                docker_args=["--network", "host"],
                delay=delay.mqtt_broker)
            self.processes.append(self._mqtt_process)

            test_utils.wait_for_port(
                host=self._mqtt_address, port=MQTT_PORT, timeout=120)
            time.sleep(2)  # Let Mosquitto start and stabilize

            # Start postgreSQL db
            print("Starting postgreSQL db", flush=True)
            self._postgres_database, postgres_address = \
                self.run_docker(image="//app/tests/test_utils:postgres-database-img-bundle",
                                docker_args=["--network", "host",
                                             "-p", f"{POSTGRES_PORT}:{POSTGRES_PORT}",
                                             "-e", "POSTGRES_PASSWORD=postgres",
                                             "-e", "POSTGRES_DB=mission",
                                             "-e", "POSTGRES_INITDB_ARGS=\
                        --auth-host=scram-sha-256 --auth-local=scram-sha-256"],
                                args=["postgres"],
                                delay=delay.postgres)
            self.processes.append(self._postgres_database)
            test_utils.wait_for_port(
                host=postgres_address, port=POSTGRES_PORT, timeout=120)

            # Start Mission Simulator
            print("Starting Mission Simulator", flush=True)
            self._sim_process, _ = self.run_docker(
                "//app/tests/test_utils:mission-simulator-img-bundle",
                docker_args=[
                    "--network", "host"],
                args=["--robots", " ".join(str(robot) for robot in self._robots),
                      "--speed", str(SIM_SPEED),
                      "--mqtt_port", str(MQTT_PORT),
                      "--mqtt_host", self._mqtt_address,
                      "--mqtt_transport", str(
                    MQTT_TRANSPORT),
                    "--mqtt_ws_path", str(
                    MQTT_WS_PATH),
                    "--mqtt_prefix", str(
                    MQTT_PREFIX)])
            self.processes.append(self._sim_process)
            time.sleep(2)  # Give the simulator a bit of time to start up.

            # Start Mission Database
            print("Starting Mission Database", flush=True)
            self._database_process, self._database_address = \
                self.run_docker(image="//app/tests/test_utils:mission-database-img-bundle",
                                docker_args=["--network", "host"],
                                args=["--port", str(DATABASE_PORT),
                                      "--controller_port", str(
                                          DATABASE_CONTROLLER_PORT),
                                      "--db_port", str(POSTGRES_PORT),
                                      "--address", "0.0.0.0"])
            self.processes.append(self._database_process)
            # Wait for both broker and db to start
            test_utils.wait_for_port(
                host=self._database_address, port=DATABASE_CONTROLLER_PORT, timeout=120)
            
            self.mission_database_config = {
                "base_url": f"http://{self._database_address}:{DATABASE_PORT}"}

            # Start Waypoint Graph Generator
            print("Starting Waypoint Graph Generator", flush=True)
            self._wpg_process, self._wpg_address = self.run_docker(
                "//app/tests/test_utils:waypoint-graph-generator-img-bundle",
                docker_args=["--network", "host", "--gpus", "all",
                            "-v", f"{CONFIG_DIR}:/app/visualizations"],
                args=["python", "scripts/rest_api.py"])
            self.processes.append(self._wpg_process)
            test_utils.wait_for_port(
                host=self._wpg_address, port=WPG_PORT, timeout=120)

            # Start cuOpt
            print("Starting cuOpt", flush=True)
            self._cuopt_container_id, self._cuopt_address = self.run_docker_shelless(
                "//app/tests/test_utils:cuopt-img-bundle",
                docker_args=["--gpus", "all",
                             "--network", "host",
                             "--env", f"CUOPT_SERVER_PORT={CUOPT_PORT}"],
                args = [])
            self.containers.append(self._cuopt_container_id)
            test_utils.wait_for_port(
                host=self._cuopt_address, port=CUOPT_PORT, timeout=1200)

            # Override services config with dynamic addresses
            # Since _database_address comes from run_docker which now returns the DinD IP (via DOCKER_HOST fix),
            # we should assume all host-networked containers are on that same IP.
            host_ip = self._database_address
            
            # Apply dynamic overrides to the config object
            dynamic_overrides = {
                "services": {
                    "mission_database": {
                        "base_url": f"http://{host_ip}:{DATABASE_CONTROLLER_PORT}"
                    },
                    "mission_dispatch": {
                        "base_url": f"http://{host_ip}:5002"
                    },
                    "waypoint_graph": {
                         "base_url": f"http://{self._wpg_address}:{WPG_PORT}"
                    },
                    "cuopt": {
                        "base_url": f"http://{self._cuopt_address}:{CUOPT_PORT}"
                    }
                }
            }
            self.config._merge_overrides(self.config._config, dynamic_overrides)
            
            config_volume = self.create_docker_volume_from_dir(CONFIG_DIR)

            self.cuopt_client = CuOptClient(
                self.config.get_cuopt_config(), client=async_client)
            time.sleep(2)
            self.wpg_client = WaypointGraphGeneratorClient(
                self.config.get_wpg_config(), client=async_client)
            self.mission_dispatch_client = MissionDispatchClient(
                self.config.get_mission_dispatch_config(), client=async_client)
            self.mission_database_client = MissionDatabaseClient(
                self.config.get_mission_database_config(), client=async_client)

            # Start mission control
            if config_overrides:
                # Generate a unique filename to avoid conflicts
                unique_filename = f"runtime_config_{uuid.uuid4().hex}.yaml"
                temp_config_path = os.path.join(TEMP_CONFIG_DIR, unique_filename)

                with open(temp_config_path, "w", encoding="utf-8") as temp_config:
                    yaml.dump(self.config._config, temp_config)

                # Use the temp config mount point
                config_arg = f"/temp_config/{unique_filename}"

                # Use a docker volume to store the config file for remote docker daemons
                temp_config_volume = self.create_docker_volume_from_dir(temp_config_path)
                # Ensure the file gets cleaned up even if the test fails
                def cleanup_temp_config():
                    try:
                        if os.path.exists(temp_config_path):
                            os.remove(temp_config_path)
                        if config_volume:
                            test_utils.remove_docker_volume(config_volume)
                        if temp_config_volume:
                            test_utils.remove_docker_volume(temp_config_volume)
                    except Exception as e:  # pylint: disable=broad-except
                        logging.error("Failed to cleanup temp config: %s", e)

                # Register cleanup function to run at exit
                atexit.register(cleanup_temp_config)
            else:
                # Use the original config file
                config_arg = config_file

            # Mount both the original config dir and our temp directory
            docker_args = ["--network", "host",
                           "-v", f"{config_volume}:/config",
                           "-e", f"AWS_ACCESS_KEY_ID={os.environ.get('AWS_ACCESS_KEY_ID', '')}",
                           "-e", f"AWS_SECRET_ACCESS_KEY={os.environ.get('AWS_SECRET_ACCESS_KEY', '')}",
                           "-e", f"AWS_REGION={os.environ.get('AWS_REGION', '')}",
                           "-e", f"AWS_ENDPOINT_URL={os.environ.get('AWS_ENDPOINT_URL', '')}"]
            if config_overrides:
                docker_args.extend(["-v", f"{temp_config_volume}:/temp_config"])

            # Optionally pass through CPU fallback env var if set in host
            mc_fallback_env = os.environ.get("MC_ENABLE_CPU_FALLBACK")
            if mc_fallback_env is not None and mc_fallback_env != "":
                docker_args.extend(["-e", f"MC_ENABLE_CPU_FALLBACK={mc_fallback_env}"])

            print("Starting mission control", flush=True)
            self._control_process, self._control_address = self.run_docker(
                "//app:mission-control-img-bundle",
                docker_args=docker_args,
                args=["--config", config_arg])
            self.processes.append(self._control_process)
            test_utils.wait_for_port(
                host=self._control_address, port=MC_PORT, timeout=120)
            # Create mission control client (use actual container address not hardcoded localhost)
            self.mission_control_config = {
                "base_url": f"http://{self._control_address}:{MC_PORT}"}

            # Start mission dispatch (after mission control so we have _control_address)
            self._md_process, _ = self.run_docker(
                "//app/tests/test_utils:mission-dispatch-img-bundle",
                docker_args=["--network", "host"],
                args=["--mqtt_port", str(MQTT_PORT),
                      "--mqtt_host", self._mqtt_address,
                      "--mqtt_transport", str(MQTT_TRANSPORT),
                      "--mqtt_ws_path", str(MQTT_WS_PATH),
                      "--mqtt_prefix", str(MQTT_PREFIX),
                      "--log_level", "DEBUG",
                      "--database_url", f"http://{self._database_address}:{DATABASE_CONTROLLER_PORT}",
                      "--mission_ctrl_url", f"http://{self._control_address}:{MC_PORT}"],
                delay=delay.mission_dispatch)
            self.processes.append(self._md_process)

            print("Test context initialized", flush=True)
        
        except Exception:
            self._cleanup_resources()
            raise

    def run_docker(self, image: str, args: list[str], docker_args: list[str],
                   delay: int = 0) -> tuple[multiprocessing.Process, str]:
        pid = os.getpid()
        queue: Any = multiprocessing.Queue()

        def wrapper_process():
            docker_process = None
            # Generate name here so we can clean up even if startup fails
            container_name = f"bazel-test-{str(uuid.uuid4())}"
            # Use a list to simulate mutable boolean for closure access
            should_notify_parent = [True]
            
            def cleanup_handler(signum, frame):
                should_notify_parent[0] = False
                # Force kill the container by name first - most reliable method
                if container_name:
                    try:
                        test_utils.kill_container(container_name)
                    except Exception:
                        pass

                if docker_process:
                    try:
                        docker_process.terminate()
                        try:
                            docker_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            docker_process.kill()
                    except Exception:
                        pass
                sys.exit(0)

            # Register handler to ensure docker process is killed on termination
            signal.signal(signal.SIGTERM, cleanup_handler)

            try:
                # Pass name to run_docker_target
                docker_process, address, _ = \
                    test_utils.run_docker_target(
                        image, args=args, docker_args=docker_args, delay=delay, name=container_name)
                queue.put(address)
                docker_process.wait()
            except Exception as e:
                print(f"Docker wrapper failed: {e}")
            finally:
                # Only notify parent if we weren't terminated intentionally
                if should_notify_parent[0]:
                    os.kill(pid, signal.SIGUSR1)

        process = multiprocessing.Process(target=wrapper_process, daemon=True)
        process.start()
        try:
            return process, queue.get()
        except Exception:
            # If an error occurs during startup (e.g. signal caught), terminate the wrapper
            # which will trigger its cleanup handler to kill the container
            process.terminate()
            process.join()
            raise

    def run_docker_shelless(self, image: str, args: list[str],
                            docker_args: list[str]) -> tuple[str, str]:
        docker_container_id, address = \
            test_utils.run_docker_target_shelless(
                image, args=args, docker_args=docker_args)

        return docker_container_id, address

    def catch_signal(self, s, f):
        for container_id in self.containers:
            test_utils.kill_container(container_id)
        TestContext.crashed_process = True
        raise OSError("Child process crashed!")

    def kill_containers(self):
        for container_id in self.containers:
            test_utils.kill_container(container_id)
        self.containers.clear()

    def create_docker_volume_from_dir(self, dir_path: str):
        volume_name = f"mc-cfg-vol-{uuid.uuid4().hex[:8]}"
        test_utils.create_docker_volume_from_dir(dir_path, volume_name)
        return volume_name

    def _cleanup_resources(self):
        # Send termination signals to all processes first for parallel cleanup
        for p in self.processes:
            if p is not None:
                p.terminate()
        
        # Then wait for them to exit
        for p in self.processes:
            if p is not None:
                p.join()
                
        self.kill_containers()

    def cleanup(self, s, f):
        self._cleanup_resources()
        print(f"SIGTERM caught, closing context: {self._name}", flush=True)
        raise SystemExit("SIGTERM caught, closing context")

    async def __aenter__(self):
        """Async enter context"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit context"""
        self._cleanup_resources()
        # Wait longer for ports to be released (--network host mode requires cleanup time)
        await asyncio.sleep(5)
        print(f"Async Context closed: {self._name}", flush=True)

    # Keep the regular context manager methods for backward compatibility
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._cleanup_resources()
        # Wait longer for ports to be released (--network host mode requires cleanup time)
        time.sleep(5)
        print(f"Context closed: {self._name}", flush=True)


async def wait_for_mission_to_complete(ctx: TestContext,
                                       mission_name: str,
                                       timeout: int = 3600):
    """
    Wait until the mission completed.
    """
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=timeout)

    while datetime.now() < end_time:
        try:
            watch_mission = \
                objects.MissionObjectV1(**await ctx.mission_dispatch_client.make_request_with_logs(
                    "get", ctx.mission_dispatch_client.base_url + "/mission/" + mission_name,
                    "Mission not found", "Mission found"))
        except HTTPError as exc:
            logging.warning("Mission query error: %s", exc)

        if watch_mission.status.state.done:
            return watch_mission.status.state.value

    logging.error("Mission %s doesn't finish within %s s",
                  mission_name, timeout)


def get_test_config(config_key: TestConfigKey):
    """Get test configuration overrides for a specific test.

    Args:
        config_key: Key from TestConfigKey enum

    Returns:
        Dictionary of configuration overrides or None
    """
    with open("app/config/test_overrides.yaml", "r", encoding="utf-8") as file:
        all_overrides = yaml.safe_load(file)

    return all_overrides.get(config_key.value)


def verify_objective_node_states(objective_tree: Union[ObjectiveCompositeNode,
                                                    ObjectiveBehaviorNode,
                                                    ObjectiveDecoratorNode,
                                                    None],
                                 expected_tree: dict) -> bool:
    """ Verify the node states of an objective with BFS traversal """

    if objective_tree is None:
        return False
    objective_queue = [objective_tree]
    expected_queue = [expected_tree]

    while objective_queue and expected_queue:
        objective_node = objective_queue.pop(0)
        expected_node = expected_queue.pop(0)

        assert objective_node.node_class.value == expected_node["node_class"]
        assert objective_node.node_type.value == expected_node["node_type"]

        if objective_node.state.value != expected_node["state"]:
            return False
        if isinstance(objective_node, ObjectiveCompositeNode):
        # objective_node.node_class == "COMPOSITE":
            objective_queue.extend(objective_node.children)
            expected_queue.extend(expected_node["children"])
        # elif objective_node.node_class == "BEHAVIOR":
        elif isinstance(objective_node, ObjectiveDecoratorNode):
            objective_queue.append(objective_node.child)
            expected_queue.append(expected_node["child"])
    if objective_queue or expected_queue:
        return False
    return True
