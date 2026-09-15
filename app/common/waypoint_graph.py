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

import pydantic


class WaypointGraph(pydantic.BaseModel):
    """ Holds the Way Point Graph data """
    nodes: list = pydantic.Field(..., description="list of nodes")
    edges: list = pydantic.Field(..., description="list of edges")
    offsets: list = pydantic.Field(..., description="list of offsets")
    weights: list = pydantic.Field(..., description="list of weights")
    map_id: str = pydantic.Field(..., description="map id")

    def get_graph_edges_offsets_weights(self):
        """ Return Edges / Offsets / Weights """
        return {"edges": self.edges, "offsets": self.offsets, "weights": self.weights}

    def get_maximum_weight(self):
        """ Return the max reasonable weight in the graph that's not an obstacle """
        # Generally magic number, use to limit the weight of the graph
        # Set higher if you have exceptionally large maps with long routes.
        max_weight = max(self.weights)
        return max_weight if max_weight <= 50 else 50
