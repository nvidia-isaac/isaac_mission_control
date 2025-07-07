# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import enum
import logging
from typing import Dict, Union


class Timeframe(enum.Enum):
    RUNTIME = "RUNTIME"
    DAILY = "DAILY"
    MISSION = "MISSION"


class TelemetryBase:
    """ Base telemetry class """
    data: dict = {}
    send_telemetry: bool = False
    metrics_env: str = "DEV"

    def __init__(self, send_telemetry: bool = False,
                 ssa_client_id: str = "",
                 ssa_client_secret: str = "",
                 metrics_env: str = "DEV"):
        """
        Initialize the TelemetryBase object.
        """
        self.data = {}
        self.send_telemetry = False  # Always disabled in base version
        self.metrics_env = metrics_env
        self.logger = logging.getLogger("Isaac Mission Control")

    def add_kpi(self, name: str, value: Union[float, dict, str], frequency: Timeframe):
        """
        Add a scalar KPI to telemetry data.

        Args:
            name (str): The name of the KPI.
            value (float): The scalar value of the KPI.
            frequency (Timeframe): The frequency at which the KPI should be recorded.
        """
        if frequency not in self.data:
            self.data[frequency] = {}
        self.data[frequency][name] = value

    def aggregate_scalar_kpi(self, name: str, value: float, frequency: Timeframe):
        """
        Calculate statistics or aggregate values for a specific KPI.

        Args:
            name (str): The name of the KPI.
            value (float): The scalar value of the KPI.
            frequency (Timeframe): The frequency at which the KPI should be recorded.
        """
        if frequency not in self.data:
            self.data[frequency] = {}
        self.data[frequency][name] = self.data[frequency].get(name, 0) + value

    def get_kpis_by_frequency(self, frequency: Timeframe):
        """
        Retrieve KPIs for a specific frequency.

        Args:
            frequency (Timeframe): The frequency for which KPIs should be retrieved.

        Returns:
            dict: A dictionary containing the KPIs for the specified frequency.
        """
        return self.data.get(frequency, {})

    def clear_frequency(self, frequency: Timeframe):
        """
        Clear all KPIs for a specific frequency.

        Args:
            frequency (Timeframe): The frequency for which to clear all KPIs.
        """
        if frequency in self.data:
            self.data[frequency] = {}

    def transmit_telemetry(self, metrics: Dict,
                           collector_id: str = "",
                           service_name: str = ""):
        """
        Stub implementation that logs but doesn't send data.

        Args:
            metrics: metric dictionary (not sent in base version)
            collector_id: stub parameter
            service_name: stub parameter
        """
        self.logger.debug("Telemetry is disabled in the base version")
