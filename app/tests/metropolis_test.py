# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2022-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import unittest

from app.api.clients import metropolis_client
from app.common.waypoint_graph import WaypointGraph

# Sample graph data in CSR format
# The graph is taken from the doc:
# https://docs.google.com/document/d/1bvnx9RFUgp9fBo7q8FxNCPEGHvrTXI8sVPfr3xCg7oI
graph = WaypointGraph(
    offsets=[0, 2, 4, 6, 8, 10, 10],
    edges=[1, 2, 2, 3, 1, 4, 2, 5, 3, 5],
    weights=[16.0, 13.0, 10.0, 12.0, 4.0, 14.0, 9.0, 20.0, 7.0, 4.0],
    nodes=[
        {"x": 6.1, "y": 8.8},
        {"x": 5.946153846153846, "y": 13.653846153846155},
        {"x": 6.536363636363636, "y": 41.56363636363636},
        {"x": 6.416666666666668, "y": 14.333333333333336},
        {"x": 6.538461538461539, "y": 47.93846153846154},
        {"x": 6.4, "y": 15.05},
    ],
    map_id="test",
)

metropolis_data = metropolis_client.UniqueObjectsLocations(
    place="", timestamp="2022-08-25T00:00:00.000Z", count=12,
    locationsOfObjects=[metropolis_client.LocationItem(id="2", locations=[[6, 14]])])


class TestMetropolis(unittest.TestCase):
    """Test traffic updates with metropolis"""

    def test_weights_update(self):
        """ Test weights update """
        traffic_updater = metropolis_client.TrafficUpdater(graph)
        updated_weights, affected_nodes, affected_edges = \
            traffic_updater.update_graph_weights_with_traffic(
                metropolis_data, proximity_threshold=2.0, scaling_factor=1.0)
        self.assertEqual(updated_weights,
                         [27.85, 13.0, 17.41, 34.51, 6.96, 14.0, 14.87, 48.6, 11.56, 5.88])
        self.assertEqual(affected_nodes, [1, 3, 5])
        self.assertEqual(affected_edges, [0, 2, 3, 4, 3, 6, 7, 8, 7, 9])


if __name__ == "__main__":
    unittest.main()
