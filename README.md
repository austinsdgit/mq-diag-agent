# MQ Diagnostic Agent - DEADQ Monitor

A real-time IBM MQ Dead Letter Queue (DEADQ) monitoring system with AI-powered recommendations and action approval workflow.

## 🎯 Overview

This agent proactively monitors the DEADQ on an IBM MQ queue manager and sends real-time alerts to a web UI when messages arrive. It provides AI-generated recommendations and allows operators to approve actions like deleting or requeuing messages.

## 🏗️ Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────┐
│   IBM MQ        │◄────────│  MQ Diag Agent   │◄────────│   Web UI    │
│   QMGRNHA       │  MCP    │  (Backend)       │ WebSocket│  (Browser)  │
│   - DEADQ       │  Server │  - Monitor       │         │  - Alerts   │
│                 │         │  - AI Analysis   │         │  - Actions  │
└─────────────────┘         └──────────────────┘         └─────────────┘
```

### Components

1. **Backend Monitor** (`backend/monitor.py`)
   - Connects to IBM MQ via MCP server
   - Non-destructively browses DEADQ every 5 seconds
   - Tracks message IDs to prevent duplicate alerts
   - Analyzes messages with AI recommendations
   - Sends alerts via WebSocket

2. **FastAPI Server** (`backend/main.py`)
   - Serves the web UI
   - Manages WebSocket connections
   - Handles action approval requests
   - Executes approved actions via MCP

3. **Web UI** (`frontend/index.html`)
   - Real-time alert dashboard
   - Message details and AI recommendations
   - Action approval workflow
   - Browser notifications

## 🚀 Deployment

### Current Deployment

- **URL**: https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com
- **Namespace**: mq-diag-agent
- **Image**: austinsd/mq-diag-agent:v5
- **Queue Manager**: QMGRNHA
- **Status**: ✅ Running and Monitoring

### Environment Variables

```bash
IBMMQ_QUEUE_MANAGER=QMGRNHA
IBMMQ_HOST=qmgrnha-ibm-mq.mq-standalone.svc.cluster.local
IBMMQ_PORT=1414
IBMMQ_CHANNEL=SYSTEM.DEF.SVRCONN
MCP_CURRENT_USER_ID=admin_user
DEADQ_NAME=DEADQ
```

### Deploy to OpenShift

```bash
# Build and push Docker image
cd mq-diag-agent
docker build --no-cache -t austinsd/mq-diag-agent:v6 .
docker push austinsd/mq-diag-agent:v6

# Update deployment
sed -i '' 's/austinsd\/mq-diag-agent:v5/austinsd\/mq-diag-agent:v6/g' k8s-deployment.yaml
oc apply -f k8s-deployment.yaml

# Check status
oc get pods -n mq-diag-agent
oc logs deployment/mq-diag-agent -n mq-diag-agent
```

## 📋 Features

### Non-Destructive Monitoring
- Uses `MQOO_BROWSE` to read messages without removing them
- Messages remain in DEADQ until explicitly deleted or requeued
- Prevents accidental message loss

### Duplicate Prevention
- Tracks message IDs in memory using a set
- Only alerts once per unique message
- Survives pod restarts (messages already in DEADQ won't re-alert)

### AI-Powered Analysis
Each alert includes:
- **Severity Level**: Critical, High, Medium based on reason code
- **Reason Description**: Human-readable explanation
- **Recommendations**: AI-generated suggestions
- **Available Actions**: Delete, Requeue, Investigate

### Action Approval Workflow
1. User reviews alert in UI
2. Selects an action (Delete/Requeue/Investigate)
3. Confirms action in approval modal
4. Backend executes via MCP server
5. UI updates to reflect result

## 🔍 Monitoring Details

### What Gets Monitored
- **Queue**: DEADQ (configurable via `DEADQ_NAME`)
- **Frequency**: Every 5 seconds
- **Method**: Non-destructive browse
- **Tracking**: Message ID (hex format)

### Alert Information
Each alert contains:
- Message ID and Correlation ID
- Reason Code and Feedback Code
- Original Queue name
- Message preview (first 200 chars)
- Timestamp
- Severity level
- AI recommendations

### Reason Codes Detected
- `2003`: Queue Manager not available
- `2035`: Not authorized
- `2042`: Object in use
- `2085`: Unknown object name
- And many more...

## 🎨 User Interface

### Dashboard Features
- **Status Indicator**: Shows connection state (green = connected)
- **Alert List**: All DEADQ messages with severity color coding
- **Detail Panel**: Full message information and recommendations
- **Action Buttons**: Delete, Requeue, Investigate
- **Approval Modal**: Confirmation dialog for destructive actions

### Browser Notifications
- Requests permission on first load
- Shows desktop notifications for new alerts
- Works even when tab is in background

## 🧪 Testing

### Recommended: Channel-Based Testing

The proper way to test is to send a message from QMGRTEST that routes through channels to QMGRNHA and fails, ending up in DEADQ with proper dead letter headers:

```bash
# Run the automated test script
cd mq-diag-agent
./test-channel-to-deadq.sh
```

This script:
1. Configures channels between QMGRTEST and QMGRNHA
2. Creates a remote queue pointing to a non-existent queue
3. Sends a test message from QMGRTEST
4. Message routes to QMGRNHA, fails, and goes to DEADQ
5. Agent detects the new message and sends an alert
6. Shows the results in the logs

### Manual Channel Test

```bash
# Send message from QMGRTEST (will fail and go to DEADQ on QMGRNHA)
oc exec -n mq-diag-agent qmgrtest-ibm-mq-0 -- bash -c \
  "echo 'Test message via channel' | /opt/mqm/samp/bin/amqsput TEST.TO.DEADQ QMGRTEST"

# Check agent logs for new alert
oc logs deployment/mq-diag-agent -n mq-diag-agent | grep -E "(New message|Alert sent)"
```

### To See Fresh Alerts

If you want to see a new alert for existing messages, restart the agent pod to clear the tracked message IDs:

```bash
# Restart agent to clear tracked messages
oc delete pod -n mq-diag-agent -l app=mq-diag-agent

# Wait for new pod to be ready
oc wait --for=condition=ready pod -l app=mq-diag-agent -n mq-diag-agent --timeout=60s

# Now send a test message - it will trigger a new alert
cd mq-diag-agent && ./test-channel-to-deadq.sh
```

### ⚠️ Not Recommended: Direct DEADQ Testing

Sending messages directly to DEADQ bypasses the normal MQ error handling and won't include proper dead letter headers:

```bash
# This works but doesn't simulate realistic scenarios
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c \
  "echo 'Test message' | /opt/mqm/samp/bin/amqsput DEADQ QMGRNHA"
```

## 🔧 Troubleshooting

### Agent Not Starting

Check authorization:
```bash
oc logs deployment/mq-diag-agent -n mq-diag-agent | grep -i error
```

Common issue: Missing `users.json` file
- Ensure `users.json` is included in Docker image
- Verify `admin_user` has proper permissions

### WebSocket Not Connecting

1. Check route is accessible:
```bash
oc get route -n mq-diag-agent
```

2. Verify WebSocket endpoint:
```bash
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com/ws
```

3. Check browser console for connection errors

### No Alerts Appearing

1. Verify messages are in DEADQ:
```bash
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- \
  /opt/mqm/samp/bin/amqsbcg DEADQ QMGRNHA
```

2. Check agent is monitoring:
```bash
oc logs deployment/mq-diag-agent -n mq-diag-agent | grep "message(s) in DEADQ"
```

3. Verify message IDs aren't already tracked (restart pod to clear):
```bash
oc delete pod -n mq-diag-agent -l app=mq-diag-agent
```

## 📊 Logs and Monitoring

### View Agent Logs
```bash
# Real-time logs
oc logs -f deployment/mq-diag-agent -n mq-diag-agent

# Filter for monitoring activity
oc logs deployment/mq-diag-agent -n mq-diag-agent | grep -E "(monitor|DEADQ|Alert)"

# Check WebSocket connections
oc logs deployment/mq-diag-agent -n mq-diag-agent | grep WebSocket
```

### Health Check
```bash
curl https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com/health
```

## 🔐 Security

### MCP Authorization
- Uses `users.json` for MCP server authentication
- Current user: `admin_user` with admin role
- Permissions defined in `users.json`

### TLS/HTTPS
- Route configured with edge termination
- WebSocket upgrades to WSS automatically
- Certificates managed by OpenShift

## 📝 Configuration Files

### Key Files
- `backend/monitor.py` - Core monitoring logic
- `backend/main.py` - FastAPI server
- `frontend/index.html` - Web UI
- `Dockerfile` - Container image definition
- `k8s-deployment.yaml` - Kubernetes resources
- `users.json` - MCP authorization
- `.env` - Environment configuration

### Customization

To monitor a different queue:
```yaml
# In k8s-deployment.yaml
env:
- name: DEADQ_NAME
  value: "YOUR.QUEUE.NAME"
```

To change polling interval:
```python
# In backend/monitor.py
await asyncio.sleep(10)  # Change from 5 to 10 seconds
```

## 🎯 Future Enhancements

- [ ] Persistent message tracking (database)
- [ ] Historical alert dashboard
- [ ] Email/Slack notifications
- [ ] Custom action scripts
- [ ] Multi-queue monitoring
- [ ] Alert filtering and search
- [ ] Export alerts to CSV/JSON
- [ ] Integration with monitoring tools (Prometheus, Grafana)

## 📚 Related Documentation

- [IBM MQ Documentation](https://www.ibm.com/docs/en/ibm-mq)
- [MCP Server Documentation](../ibm-mq-mcp-server/README.md)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)

## 🤝 Contributing

This agent was created as part of the bob_work project. To contribute:

1. Make changes to the code
2. Build and test locally
3. Update version in k8s-deployment.yaml
4. Deploy to OpenShift
5. Document changes in this README

## 📄 License

Part of the bob_work project.

---

**Status**: ✅ Production Ready
**Last Updated**: 2026-05-26
**Version**: v5
