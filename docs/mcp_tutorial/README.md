# Mission Control MCP Tutorial (Cursor)

This tutorial explains how to run the Mission Control MCP server from this repo and connect it to Cursor.

## Requirements

- Ubuntu/Linux environment (validated on Ubuntu 24.04)
- Python 3.10+
- Cursor installed (v2.4+ recommended)
- Install and launch Isaac Sim using the [Isaac ROS Isaac Sim Setup Guide](https://nvidia-isaac-ros.github.io/getting_started/index.html)
- Launch Mission Control services first using the [Mission Control Tutorial](https://github.com/nvidia-isaac/isaac_mission_control/blob/main/docs/tutorial/tutorial.md) (this bringup starts both Mission Control and Mission Dispatch)
- Isaac Sim setup and Mission Control service bringup can be done in parallel
- Mission Control backend reachable (default: `http://localhost:8050`)

Quick health check:

```bash
curl http://localhost:8050/api/v1/health
```

## 1) Set up the MCP package

From the repository root:

```bash
cd app/agentic-utilities/mission-control-mcp
python3 -m venv venv
./venv/bin/python -m pip install -U pip
./venv/bin/python -m pip install -e .
```

## 2) Configure Cursor MCP directly in `mcp.json`

Edit `~/.cursor/mcp.json` (or use Cursor Settings -> MCP and Integration, which writes this file).

Add/update this server entry with your real local paths:

```json
{
  "mcpServers": {
    "mission-control": {
      "command": "bash",
      "args": [
        "-lc",
        "set -euo pipefail; cd \"/ABS/PATH/TO/mission-control/app/agentic-utilities/mission-control-mcp\" && exec \"/ABS/PATH/TO/mission-control/app/agentic-utilities/mission-control-mcp/venv/bin/python\" -m mission_control_mcp.server"
      ],
      "env": {
        "MISSION_CONTROL_URL": "http://localhost:8050"
      }
    }
  }
}
```

Notes:

- Replace `/ABS/PATH/TO/mission-control` with your actual path.
- If Mission Control is remote or port-forwarded, change `MISSION_CONTROL_URL` accordingly.
- No `.env` file is required for this flow.

## 3) Enable and verify in Cursor

- Open Cursor Settings -> MCP and Integration.
- Enable the `mission-control` server.
- Start a new chat and ask:
  - `Use Mission Control to test the connection.`

If configured correctly, the server should respond with a successful connection result.

## 4) Stability notes

The MCP tools **`submit_charging_mission`** and **`submit_undock_mission`** may be unstable. Use them with caution and prefer other tools when possible.

## 5) Troubleshooting

- **Connection refused**
  - Confirm Mission Control is reachable at the configured `MISSION_CONTROL_URL`.
- **Tools do not appear**
  - Disable/re-enable the MCP server in Cursor settings.
  - Start a new chat.
  - Restart Cursor.
- **Check server logs**
  - `/tmp/mission_control_mcp.log`

## Implementation references

- MCP server tools: `app/agentic-utilities/mission-control-mcp/src/server.py`
- Mission Control API client used by the MCP server: `app/agentic-utilities/mission-control-mcp/src/queries.py`

