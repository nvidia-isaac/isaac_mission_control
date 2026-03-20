"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""

import asyncio
import typing
import logging

import py_trees
from cloud_common.objects import objective
from app.core.objectives.objectives_conditional import ConditionalExpression, evaluate_conditional

logger = logging.getLogger("Isaac Mission Control")


def tree2objective_state(type: py_trees.common.Status) -> objective.ObjectiveStateV1:
    if type == py_trees.common.Status.SUCCESS:
        return objective.ObjectiveStateV1.COMPLETED
    elif type == py_trees.common.Status.FAILURE:
        return objective.ObjectiveStateV1.FAILED
    elif type == py_trees.common.Status.RUNNING:
        return objective.ObjectiveStateV1.RUNNING
    else:
        return objective.ObjectiveStateV1.PENDING


def objective2tree_state(type: objective.ObjectiveStateV1) -> py_trees.common.Status:
    if type == objective.ObjectiveStateV1.COMPLETED:
        return py_trees.common.Status.SUCCESS
    elif type == objective.ObjectiveStateV1.RUNNING:
        return py_trees.common.Status.RUNNING
    elif type == objective.ObjectiveStateV1.PENDING:
        return py_trees.common.Status.INVALID
    else:
        return py_trees.common.Status.FAILURE

class ObjectiveLeafNode(py_trees.behaviour.Behaviour):
    """
    Behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveBehaviorNode,
                 running_nodes: list, status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.node_type = objective_node.node_type
        self.running_nodes = running_nodes
        self.status = status
        self.completed = False
        super(ObjectiveLeafNode, self).__init__(  # pylint: disable=super-with-arguments
            name=objective_node.node_type.value)

    def initialise(self):
        self.status = py_trees.common.Status.RUNNING

    def update(self) -> py_trees.common.Status:
        logger.debug("Running_nodes: %s", self.running_nodes)
        if (self.objective_node.state == objective.ObjectiveStateV1.PENDING or 
            self.objective_node.state == objective.ObjectiveStateV1.RUNNING):
            if self not in self.running_nodes:
                self.running_nodes.append(self)
                logger.debug("Leaf node initialised and added to running_nodes: %s", self.running_nodes)
            return py_trees.common.Status.RUNNING
        # The node is ticked again after it has been completed
        # This is specific to the case where this is a child of a Retry or Repeat node.
        # We need to "reset" the state of the node and make it runnable again.
        elif self.objective_node.state == objective.ObjectiveStateV1.COMPLETED and self.completed:
            self.completed = False
            self.objective_node.state = objective.ObjectiveStateV1.RUNNING
            if self not in self.running_nodes:
                self.running_nodes.append(self)
                logger.debug("Resetting COMPLETED node to RUNNING, adding to running_nodes: %s",
                            self.running_nodes)
            return py_trees.common.Status.RUNNING
        elif self.objective_node.state == objective.ObjectiveStateV1.COMPLETED and not self.completed:
            self.completed = True
            return py_trees.common.Status.SUCCESS
        else:
            return objective2tree_state(self.objective_node.state)


class SequenceNode(py_trees.composites.Sequence):
    """
    Sequence behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Sequence", memory=True)


class SelectorNode(py_trees.composites.Selector):
    """
    Selector behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Selector", memory=True)


class ParallelNode(py_trees.composites.Parallel):
    """
    Selector behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Parallel",
                         policy=py_trees.common.ParallelPolicy.SuccessOnAll())

class ConditionalNode(py_trees.decorators.Decorator):
    """
    Conditional behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveDecoratorNode,
                 child: py_trees.behaviour.Behaviour,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.condition = ConditionalExpression(**objective_node.parameters["condition"])
        self.status = status
        super().__init__(name="Conditional",
                         child=child)


    
    def tick(self) -> typing.Iterator[py_trees.behaviour.Behaviour]:
        """
        Conditionally manage the child.
        Before deciding to tick the child, we need to evaluate the condition.

        Yields:
            a reference to itself or one of its children
        """

        logger.debug(f"ConditionalNode tick: {self.condition}")
        from app.core.objectives.objectives import ObjectiveExecutor
        loop = ObjectiveExecutor.get_instance().database_event_loop
        db_client = ObjectiveExecutor.get_instance().database_client

        # Evaluate the condition inside ObjectiveExecutor's event loop
        future = asyncio.run_coroutine_threadsafe(evaluate_conditional(self.condition, db_client), loop)
        try:
            result = future.result(timeout=20)
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            self.stop(py_trees.common.Status.FAILURE)
            yield self

        if not result:
            logger.warning(f"Condition not met")
            self.stop(py_trees.common.Status.FAILURE)
            yield self
        else:
            logger.debug(f"Condition met")
            for node in self.decorated.tick():
                yield node
                # resume normal proceedings for a Behaviour's tick
                new_status = self.update()
                if new_status not in list(py_trees.common.Status):
                    logger.error(
                        "A behaviour returned an invalid status, setting to INVALID [%s][%s]"
                        % (new_status, self.name)
                    )
                    new_status = py_trees.common.Status.INVALID
                if new_status != py_trees.common.Status.RUNNING:
                    self.stop(new_status)
                self.status = new_status
                yield self

    def update(self) -> py_trees.common.Status:
        """
        Reflect the decorated child's status.

        The update method is only ever triggered in the child's post-tick, which implies
        that the condition has already been checked and passed (refer to the :meth:`tick` method).

        Returns:
            the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == py_trees.common.Status.INVALID:
            return py_trees.common.Status.RUNNING
        return self.decorated.status


class RetryNode(py_trees.decorators.Retry):
    """
    Retry behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveDecoratorNode,
                 child: py_trees.behaviour.Behaviour,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        if not objective_node.parameters.get("num_failures"):
            raise ValueError("num_failures is required for RetryNode")
        super().__init__(name="Retry",
                         child=child,
                         num_failures=objective_node.parameters["num_failures"])

class InverterNode(py_trees.decorators.Inverter):
    """
    Inverter behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveDecoratorNode,
                 child: py_trees.behaviour.Behaviour,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Inverter",
                         child=child)

class RepeatNode(py_trees.decorators.Repeat):
    """
    Repeat behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveDecoratorNode,
                 child: py_trees.behaviour.Behaviour,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        if not objective_node.parameters.get("num_success"):
            raise ValueError("num_success is required for RepeatNode")
        super().__init__(name="Repeat",
                         child=child,
                         num_success=objective_node.parameters["num_success"])
