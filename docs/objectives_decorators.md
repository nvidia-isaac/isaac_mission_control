# Objectives Decorators

Decorator nodes wrap and modify the behavior of their child nodes. They provide a way to add conditional logic, retry mechanisms, and other control flow patterns to your objectives tree.

## Conditional Decorator Node

The conditional decorator node executes its child node only when a specified condition evaluates to true. This allows for dynamic decision-making based on runtime state.

### Basic Structure

```json
{
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "parameters": {
        "condition": {
            // condition definition
        }
    },
    "child": {
        // child node definition
    }
}
```

## Condition Definition

Conditions are defined using a recursive structure that supports both simple comparisons and complex logical expressions.

### Condition Schema

```json
{
    "type": "LOGICAL_EXPRESSION" | "COMPARISON",
    "operator": "...",
    "operands": [...]
}
```

### Condition Types

#### 1. Logical Expressions

Used to combine multiple conditions with logical operators.

- **Type:** `"LOGICAL_EXPRESSION"`
- **Operators:** `"AND"`, `"OR"`
- **Operands:** Array of at least 2 elements (can be other logical expressions or comparisons)

#### 2. Comparisons

Used to compare two values.

- **Type:** `"COMPARISON"`
- **Operators:** `"EQ"` (equals), `"NEQ"` (not equals), `"LT"` (less than), `"GT"` (greater than), `"GE"` (greater or equal), `"LE"` (less or equal)
- **Operands:** Array of exactly 2 elements (string literals, floats, or database references)

## Available References

The following database references are currently available for use in conditions:

### `robot_state(robot_name)`
- **Returns:** String representing the current state of the specified robot
- **Possible values:** `"IDLE"`, `"ON_TASK"`, `"CHARGING"`
- **Example:** `"robot_state(robot_a)"`

### `robot_battery_level(robot_name)`
- **Returns:** Float representing the battery level of the specified robot (0.0 to 100.0)
- **Example:** `"robot_battery_level(robot_a)"`

## Examples

### Simple Condition

Check if a robot's battery level is above 50%:

```json
{
    "type": "COMPARISON",
    "operator": "GT",
    "operands": [
        "robot_battery_level(robot_a)",
        50
    ]
}
```

### Complex Condition

Check if a robot has sufficient battery AND is currently idle:

```json
{
    "type": "LOGICAL_EXPRESSION",
    "operator": "AND",
    "operands": [
        {
            "type": "COMPARISON",
            "operator": "GT",
            "operands": [
                "robot_battery_level(robot_a)",
                50
            ]
        },
        {
            "type": "COMPARISON",
            "operator": "EQ",
            "operands": [
                "robot_state(robot_a)",
                "IDLE"
            ]
        }
    ]
}
```

### Complete Conditional Decorator Example

A complete conditional decorator node that only executes its child when the robot is ready for a task:

```json
{
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "parameters": {
        "condition": {
            "type": "LOGICAL_EXPRESSION",
            "operator": "AND",
            "operands": [
                {
                    "type": "COMPARISON",
                    "operator": "GT",
                    "operands": [
                        "robot_battery_level(robot_a)",
                        50
                    ]
                },
                {
                    "type": "COMPARISON",
                    "operator": "EQ",
                    "operands": [
                        "robot_state(robot_a)",
                        "IDLE"
                    ]
                }
            ]
        }
    },
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "parameters": {
            ...
        }
    }
}
```

In this example, the navigation command will only execute if `robot_a` has more than 50% battery level AND is currently in the "IDLE" state.

## Retry Decorator Node

Will retry its child up to `num_failures` times on child FAILURE. On child SUCCESS, the Retry node will return SUCCESS.

```json
{
    "node_class": "DECORATOR",
    "node_type": "RETRY",
    "parameters": {
        "num_failures": 3
    },
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "parameters": {
            ...
        }
    }
}
```

## Repeat Decorator Node

Will repeat its child up to `num_success` times on child SUCCESS. Afterwards, the Repeat node will return SUCCESS. On child FAILURE, the Repeat node will return FAILURE.

```json
{
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "parameters": {
        "num_success": 2
    },
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "parameters": {
            ...
        }
    }
}
```

## Inverter Decorator Node

Will return the inverse of its child.

```json
{
    "node_class": "DECORATOR",
    "node_type": "INVERTER",
    "parameters": {},
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "parameters": {
            ...
        }
    }
}
```
