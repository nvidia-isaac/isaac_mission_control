# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging
from app.common.telemetry_base import TelemetryBase, Timeframe  # noqa: F401

logger = logging.getLogger(__name__)

# Try to import Kratos Telemetry, fallback to base if not available
try:
    from app.internal.telemetry.metrics import Telemetry  # type: ignore
    logger.info("Successfully imported internal telemetry module")
except (ImportError, ModuleNotFoundError) as e:
    # If import fails, use the base implementation
    logger.debug("Internal telemetry module not available, using base implementation: %s", str(e))
    Telemetry = TelemetryBase

# Re-export Timeframe for backward compatibility
__all__ = ["Telemetry", "Timeframe"]
