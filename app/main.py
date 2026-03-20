# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import atexit
import asyncio
import argparse
import enum
import logging
import os
import sys

import uvicorn
import httpx

from opentelemetry.sdk.resources import Resource

# opentelemetry packages
from opentelemetry import trace, metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


from fastapi import FastAPI
from contextlib import asynccontextmanager
import app.api.endpoints.mission_control_api as api
from app.core.mission_control import MissionControl
from app.core.objectives.objectives import ObjectiveExecutor
from app.core.mission_control_config import MissionControlConfig, MapConfig
from app.common.metrics import Timeframe

from pathlib import Path
from app.api.endpoints.mission_control_api import MAP_STORAGE_DIR


class VerbosityOptions(enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    DEBUG = "DEBUG"


parser = argparse.ArgumentParser(description="Mission Server Prototype")
parser.add_argument("--config", "-c", type=str, default="app/config/defaults.yaml",
                    help="Path to the yaml config file.")
parser.add_argument("--verbose", type=VerbosityOptions,
                    default=VerbosityOptions.INFO, choices=list(VerbosityOptions),
                    help="Verbosity level")
parser.add_argument("--host", type=str,
                    default="0.0.0.0", help="Mission control host.")
parser.add_argument("--port", type=int,
                    default=8050, help="Mission control port.")
parser.add_argument("--dev", action="store_true",
                    help="Enable tracebacks")
parser.add_argument("--root_path", type=str, default="",
                    help="If mission control is hosted behind a reverse proxy "
                    "set this to the url it is routed to")
parser.add_argument("--enable_mega_observability", action="store_true", default=False,
                    help="Enable observability features for MEGA deployment.")

args = parser.parse_known_args()[0]

# Create logger
logger = logging.getLogger("Isaac Mission Control")
logger.setLevel(args.verbose.value)
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s ",
    datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(stream_handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI startup")
    logger.info("Starting async Mission Control")
    app.state.client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=3),
                                         timeout=60.0)
    mc_exp = MissionControl(MissionControlConfig(
        args.config), app.state.client, app.state.otel_meters)
    # Start MC startup but do not let it block the FastAPI server
    asyncio.create_task(mc_exp.startup())

    # Initialize Objective Executor
    ObjectiveExecutor()

    # Register the map specified in the configuration so it appears in
    # /map/list even if it wasn't uploaded via the HTTP API.
    try:
        cfg = mc_exp.config.get_map_config()
        if cfg.metadata and (cfg.map_file or cfg.map_uri or cfg.map_s3):
            map_id = cfg.metadata.map_id or "default_map"
            api.app.state.available_maps[map_id] = cfg  # type: ignore[attr-defined]
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not register start-up map in available_maps: %s", exc)

    # Persisted uploads: scan MAP_STORAGE_DIR and register everything so
    # available_maps survives restarts on the same machine.
    try:
        img_patterns = ["*.png", "*.jpg", "*.jpeg"]
        for pattern in img_patterns:
            for img_path in Path(MAP_STORAGE_DIR).glob(pattern):
                map_id = img_path.stem
                if map_id in api.app.state.available_maps:  # already registered
                    continue

                metadata_yaml = img_path.with_suffix(".yaml")

                try:
                    if metadata_yaml.exists():
                        cfg = MapConfig(
                            map_file=str(img_path),
                            map_uri=None,
                            map_s3=None,
                            metadata_yaml=str(metadata_yaml),
                            metadata=None,
                            map_file_loaded=None
                        )
                    else:
                        raise ValueError("Missing metadata YAML for persisted map")

                    api.app.state.available_maps[map_id] = cfg  # type: ignore[attr-defined]
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Skipping persisted map %s: %s", img_path, exc)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Error loading persisted maps: %s", exc)

    yield
    logger.info("FastAPI shutdown")
    # Stop SAP background task before closing client
    if MissionControl.sap_background_task:
        await MissionControl.sap_background_task.stop()
    await app.state.client.aclose()
    await ObjectiveExecutor.get_instance().close()

# Use a root app to define the URL prefix for the main app.
# This will allow the main API implementation to be located at
# a custom path like /api/v1 for example without having to worry
# about handling this path in each request.
root_app = FastAPI(debug=True, lifespan=lifespan)

# Add MEGA observability
if args.enable_mega_observability:
    logger.info("NVCF observability enabled")
    # Verify that OTEL endpoints are available
    env_vars = [
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    ]
    # Check and print if each environment variable is set
    for var in env_vars:
        if var in os.environ:
            logger.debug("%s is set: %s", var, os.environ.get(var))
        else:
            logger.debug("%s is not set.", var)

    # Setup the Mission Control Resource
    service_name = "mega-mission-control"
    mega_component_name = "mission-control"
    resource = Resource(
        attributes={"service.name": service_name, "mega.component.name": mega_component_name}
    )

    # Set up Metrics
    metric_exporter = OTLPMetricExporter()
    reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=5_000
    )
    meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
    metrics.set_meter_provider(meter_provider)
    meter = meter_provider.get_meter("mega.missioncontrol")

    up = meter.create_gauge(name="up", description="The scraping was successful")
    up.set(1)

    mission_generation_duration = meter.create_histogram(
        name="mission.generation.duration",
        unit="s",
        description="Duration of HTTP requests in seconds",
    )

    root_app.state.otel_meters = {
        "up": up,
        "mission.generation.duration": mission_generation_duration
    }

    # Set up Traces
    tracer_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter()
    processor = BatchSpanProcessor(trace_exporter)
    tracer_provider.add_span_processor(processor)
    trace.set_tracer_provider(tracer_provider)

    # Add FastAPI auto-instrumentation
    FastAPIInstrumentor.instrument_app(root_app)

    # Remove logging from /GET health to reduce clutter in MEGA logs
    class HealthCheckFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "/health" not in record.getMessage()
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.addFilter(HealthCheckFilter())
else:
    root_app.state.otel_meters = None

@root_app.get("/")
def read_root():
    return {"Mission Control": "Copyright NVIDIA Corporation 2022-2025. All rights reserved"}


root_app.mount("/api/v1", api.get_mission_control_app())


if __name__ == "__main__":
    if args.dev or (args.verbose.value == VerbosityOptions.DEBUG.value):
        sys.tracebacklimit = 100  # Set an arbitrary value to enable tracebacks
    else:
        sys.tracebacklimit = 0
    uvicorn.run(root_app, host=args.host, port=args.port, root_path=args.root_path)


def mission_control_dump_telemetry_on_exit():
    """  This exit handler will dump all telemetry data before exiting """

    mc = MissionControl.get_instance()
    if mc.telemetry.send_telemetry is True:
        for timeframe in Timeframe:
            mc.telemetry.transmit_telemetry(
                mc.telemetry.get_kpis_by_frequency(timeframe))
            mc.telemetry.clear_frequency(timeframe)


atexit.register(mission_control_dump_telemetry_on_exit)
