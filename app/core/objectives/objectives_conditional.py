"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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

import pydantic.v1 as pydantic
import asyncio
from enum import Enum
import re
from typing import Union
from app.api.clients.mission_database_client import MissionDatabaseClient
import logging

logger = logging.getLogger("Isaac Mission Control")

class ConditionalOperator(str, Enum):
    # Logical Operators
    AND = "and"
    OR = "or"

    # Comparison Operators
    EQUAL = "eq"
    NOT_EQUAL = "neq"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "ge"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "le"

    @property
    def is_logical_operator(self):
        return self in (self.AND, self.OR)

class ConditionalType(str, Enum):
    LOGICAL_EXPRESSION = "logical_expression"
    COMPARISON = "comparison"

class ConditionalExpression(pydantic.BaseModel):
    type: ConditionalType
    operator: ConditionalOperator
    operands: list[Union["ConditionalExpression", str, float]]

    @pydantic.validator("type", pre=True)
    def type_validator(cls, value):
        if isinstance(value, str):
            value = value.lower()
        return value

    @pydantic.validator("operator", pre=True)
    def operator_validator(cls, value):
        if isinstance(value, str):
            value = value.lower()
        return value

    @pydantic.root_validator()
    def operands_validator(cls, values):
        if values.get("type") == ConditionalType.LOGICAL_EXPRESSION:
            if not values.get("operator").is_logical_operator:
                raise ValueError("Logical expression must have a logical operator")
            if len(values.get("operands")) < 2:
                raise ValueError("Logical expression must have at least two operands")
        elif values.get("type") == ConditionalType.COMPARISON:
            if values.get("operator").is_logical_operator:
                raise ValueError("Comparison must have a comparison operator")
            if len(values.get("operands")) != 2:
                raise ValueError("Comparison must have exactly two operands")
        return values

ConditionalExpression.update_forward_refs()

async def _evaluate_logical_expression(expression: ConditionalExpression, db_client: MissionDatabaseClient) -> bool:
    evaluated_operands = await asyncio.gather(*[evaluate_conditional(operand, db_client) for operand in expression.operands])

    if expression.operator == ConditionalOperator.AND:
        return all(evaluated_operands)
    elif expression.operator == ConditionalOperator.OR:
        return any(evaluated_operands)
    else:
        raise ValueError(f"Invalid logical operator: {expression.operator}")

async def _evaluate_comparison(expression: ConditionalExpression, db_client: MissionDatabaseClient) -> bool:
    try:
        left, right = await asyncio.gather(
            dereference(expression.operands[0], db_client),
            dereference(expression.operands[1], db_client)
        )
    except Exception as e:
        logger.error(f"Error dereferencing operands: {e}")
        return False

    # if both are numbers, compare as floats, otherwise compare as strings
    if is_number(left) and is_number(right):
        left = float(left)
        right = float(right)
    else:
        left = str(left).lower()
        right = str(right).lower()

    if expression.operator == ConditionalOperator.EQUAL:
        return left == right
    elif expression.operator == ConditionalOperator.NOT_EQUAL:
        return left != right
    elif expression.operator == ConditionalOperator.GREATER_THAN:
        return left > right
    elif expression.operator == ConditionalOperator.GREATER_THAN_OR_EQUAL:
        return left >= right
    elif expression.operator == ConditionalOperator.LESS_THAN:
        return left < right
    elif expression.operator == ConditionalOperator.LESS_THAN_OR_EQUAL:
        return left <= right
    else:
        raise ValueError(f"Invalid comparison operator: {expression.operator}")

async def evaluate_conditional(expression: ConditionalExpression, db_client: MissionDatabaseClient) -> bool:
    logger.debug(f"Evaluating conditional expression: {expression}")
    if expression.type == ConditionalType.LOGICAL_EXPRESSION:
        return await _evaluate_logical_expression(expression, db_client)
    elif expression.type == ConditionalType.COMPARISON:
        return await _evaluate_comparison(expression, db_client)
    else:
        raise ValueError(f"Invalid expression type: {expression.type}")

regex_map = {
    "robot_state": r"robot_state\((.*)\)",
    "robot_battery_level": r"robot_battery_level\((.*)\)"
}

async def dereference(ref: str, db_client: MissionDatabaseClient):
    for key, regex in regex_map.items():
        match = re.fullmatch(regex, ref)
        if match:
            arg = match.group(1)
            if key == "robot_state":
                result = (await db_client.get_robot(arg)).status.state.value
                return result
            elif key == "robot_battery_level":
                result = (await db_client.get_robot(arg)).status.battery_level
                return result
    # If no match, return the string as is
    return ref

def is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False

