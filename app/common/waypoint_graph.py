# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import pydantic.v1 as pydantic


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
