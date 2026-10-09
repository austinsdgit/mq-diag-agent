# MQ Diagnostic Agent - Deployment Status

## Current Status: Authorization Issue

The agent is built and deployed but failing to start due to MCP server authorization checks.

## Issue

```
User 'admin_user' does not have permission to perform action 'connect'
```

## Root Cause

The MCP server's authorization system is checking permissions even though we're connecting directly via `mq_client.connect()`. The `users.json` file exists but may not be loaded correctly.

## What We've Done

1. ✅ Created `users.json` with correct format
2. ✅ Added users.json to Dockerfile
3. ✅ Set MCP_CURRENT_USER_ID=admin_user in .env
4. ✅ Using direct MQ connection (bypasses MCP tools)

## Solution Options

### Option 1: Disable Authorization (Simplest)

The custom-mq-agent works because it connects directly without authorization checks. We need to either:

1. Set an environment variable to disable authorization
2. Or ensure the MCP server loads users.json from the correct path

### Option 2: Verify File Path

The MCP server looks for `users.json` in the current working directory. Since we run from `/app/backend`, we need to ensure the file is there or set the path explicitly.

**Add to .env:**
```bash
USERS_CONFIG_PATH=/app/users.json
```

Or copy to backend directory in Dockerfile:
```dockerfile
RUN cp /app/users.json /app/backend/users.json
```

### Option 3: Use Direct pymqi Connection

Bypass the MCP server entirely and connect directly with pymqi:

```python
import pymqi

qmgr = pymqi.connect(
    queue_manager_name,
    channel,
    conn_info,
    user,
    password
)
```

## Recommended Next Step

**Try Option 2 first** - Add environment variable to specify users.json path:

1. Update `.env`:
   ```bash
   USERS_CONFIG_PATH=/app/users.json
   ```

2. Or update Dockerfile to copy file:
   ```dockerfile
   RUN cp /app/users.json /app/backend/users.json
   ```

3. Rebuild and redeploy:
   ```bash
   ./deploy.sh build
   oc rollout restart deployment/mq-diag-agent -n mq-diag-agent
   ```

## Files Created

- ✅ `backend/monitor.py` - DEADQ monitoring logic
- ✅ `backend/main.py` - FastAPI + WebSocket server
- ✅ `frontend/index.html` - Real-time UI
- ✅ `users.json` - MCP authorization config
- ✅ `.env` - Configuration
- ✅ `Dockerfile` - Container build
- ✅ `k8s-deployment.yaml` - OpenShift deployment
- ✅ `deploy.sh` - Deployment script
- ✅ `configure.sh` - Docker Hub configuration
- ✅ Documentation (README, QUICKSTART, DOCKER_HUB_SETUP)

## Agent Features (When Working)

- Monitors DEADQ every 5 seconds
- AI analyzes reason codes
- Real-time WebSocket alerts
- Approval-based actions
- Comprehensive recommendations

---

**Made with Bob** 🤖