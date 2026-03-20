# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging

from typing import Optional


class Task:
    """
        Representation of cuOpt task_data

        demand: used for docking in conjunction with 'capacity'
        task_locations: list of ints representing nodes for routing
        task_time_windows: used to ensure sequence in navigation mission
        prizes: used for docking to ensure only one dock is picked
    """
    demand: list[list[int]]
    task_locations: list[int]
    task_time_windows: list[list[int]]
    prizes: list[float]

    def set_task_nodes(self, nodes: list, max_weight: int):
        """
        Setter for the WayPointGraph node IDs that
        are closest to the tasks
        """
        if -1 in nodes:
            raise Exception("Task node location ID can not be negative")

        self.task_locations = nodes
        # If there are more than two tasks
        # Ensure each task is dependent on the previous one.  This will
        # instruct cuopt to travel to nodes in the prescribed order.
        # The first task is always executed, so cannot be dependent.
        self.task_time_windows = []

        # If for example we have a 100 node route, windows are [0,100],[100,200]...
        multiplier = int(len(nodes)*max_weight) + 100
        if len(nodes) >= 2:
            for i in range(len(nodes)):
                self.task_time_windows.append([int(i*multiplier),
                                               int((i+1)*multiplier)])

    def set_task_locations_with_demand_and_prizes(self, nodes: list,
                                                  demand: Optional[list] = None,
                                                  prizes: Optional[list] = None):
        """
        Setter for the WayPointGraph node IDs that
        are closest to the tasks and also cuOpt demand list.

        Used in docking
        """
        if not demand:
            self.demand = [[1] * len(nodes)]
        else:
            if len(demand) != len(nodes):
                raise ValueError("Length of demands list must be equal to the length of nodes")
            self.demand = [demand]
        if not prizes:
            self.prizes = [1] * len(nodes)
        else:
            if len(prizes) != len(nodes):
                raise ValueError("Length of prizes list must be equal to the length of nodes")
            self.prizes = prizes
        self.task_locations = nodes

    def get_task(self):
        return vars(self)

    def get_task_data(self):
        return {k: v for k, v in self.get_task().items() if v != []}
