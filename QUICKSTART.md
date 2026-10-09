# MQ Diagnostic Agent - Quick Start Guide

Get up and running with the MQ Diagnostic Agent in 5 minutes!

## 🎯 What This Does

The MQ Diagnostic Agent monitors your queue manager's Dead Letter Queue (DEADQ) and:
- ✅ Detects messages that fail to be delivered
- 🤖 Analyzes the failure reason with AI
- 💡 Recommends specific actions to fix the issue
- 🖥️ Shows everything in a real-time web UI
- ✋ Requires your approval before taking any action

## 📋 Prerequisites

- Access to an OpenShift cluster with IBM MQ
- `oc` CLI installed and logged in
- Docker installed (for building the image)

## 🚀 Deploy in 3 Steps

### Step 1: Configure Your MQ Connection

Edit the `.env` file:

```bash
cd mq-diag-agent
nano .env
```

Update these values for your queue manager:

```bash
IBMMQ_QUEUE_MANAGER=QMGRNHA          # Your queue manager name
IBMMQ_HOST=qmgrnha-ibm-mq.cp4i.svc.cluster.local  # MQ service hostname
IBMMQ_PORT=1414                       # MQ port
IBMMQ_USERNAME=mqm                    # MQ username
```

### Step 2: Deploy

Run the deployment script:

```bash
./deploy.sh all
```

This will:
1. Build the Docker image
2. Push to OpenShift registry
3. Deploy the application
4. Create a route for access

Wait for the deployment to complete (about 2-3 minutes).

### Step 3: Access the UI

Get your application URL:

```bash
./deploy.sh info
```

You'll see output like:

```
🌐 Application URL: https://mq-diag-agent-mq-diag-agent.apps.your-cluster.com
```

Open that URL in your browser!

## 🎨 Using the UI

### Dashboard

When you open the UI, you'll see:

1. **Connection Status** (top right)
   - Green dot = Connected and monitoring
   - Red dot = Disconnected

2. **Alert List** (left panel)
   - Shows all messages in the DEADQ
   - Color-coded by severity:
     - 🔴 Red = Critical
     - 🟠 Orange = High
     - 🔵 Blue = Medium

3. **Alert Details** (right panel)
   - Click any alert to see details
   - Shows recommendations and available actions

### Taking Action

When you click an alert, you can:

1. **View Full Message** - See complete message details
2. **Replay to Original Queue** - Put the message back (requires approval)
3. **Delete Message** - Remove from DEADQ (requires approval)
4. **Start Investigation** - Get queue information

For actions that require approval, you'll see a confirmation dialog.

## 🧪 Testing

Want to see it in action? Create a test scenario:

### Option 1: Send to Non-Existent Queue

```bash
# This will fail and go to DEADQ
echo "Test message" | /opt/mqm/samp/bin/amqsput NONEXISTENT.QUEUE QMGRNHA
```

### Option 2: Fill a Queue

```bash
# Create a small queue
echo "DEFINE QLOCAL(TEST.SMALL) MAXDEPTH(1)" | runmqsc QMGRNHA

# Send 2 messages (second will fail)
echo "Message 1" | /opt/mqm/samp/bin/amqsput TEST.SMALL QMGRNHA
echo "Message 2" | /opt/mqm/samp/bin/amqsput TEST.SMALL QMGRNHA
```

Within 5 seconds, you should see an alert appear in the UI!

## 📊 Monitoring

### View Logs

```bash
./deploy.sh logs
```

### Check Status

```bash
# Get deployment status
oc get all -n mq-diag-agent

# Check if pod is running
oc get pods -n mq-diag-agent
```

### Health Check

Visit: `https://your-route/health`

You should see:
```json
{
  "status": "healthy",
  "monitoring": true,
  "connected": true,
  "timestamp": "2026-05-26T15:30:00.000Z"
}
```

## 🔧 Common Issues

### "WebSocket Connection Failed"

**Solution**: Check if the pod is running:
```bash
oc get pods -n mq-diag-agent
```

If not running, check logs:
```bash
./deploy.sh logs
```

### "Cannot Connect to MQ"

**Solution**: Verify MQ connection details in `.env`:
```bash
# Test MQ connectivity from your machine
telnet qmgrnha-ibm-mq.cp4i.svc.cluster.local 1414
```

### "No Alerts Appearing"

**Solution**: 
1. Check if DEADQ actually has messages
2. Verify monitoring is active: Visit `/api/status`
3. Check logs for errors

## 🎓 Understanding the Alerts

### Severity Levels

- **Critical** 🔴: Requires immediate attention (auth failures, missing queues)
- **High** 🟠: Important issues (queue full, connection broken)
- **Medium** 🔵: Informational (message too large, general errors)

### Common Reason Codes

| Code | What It Means | Quick Fix |
|------|---------------|-----------|
| 2085 | Queue doesn't exist | Create the queue |
| 2004 | Queue is full | Increase MAXDEPTH or clear messages |
| 2035 | Not authorized | Grant permissions |
| 2003 | Message too large | Increase MAXMSGL |

## 🎯 Next Steps

Now that you're up and running:

1. **Monitor Regularly**: Keep the UI open to catch issues proactively
2. **Review Recommendations**: The AI provides specific actions for each issue
3. **Take Action**: Use the approval-based actions to resolve issues
4. **Investigate**: Use the "Start Investigation" action to gather more info

## 📚 Learn More

- Full documentation: See `README.md`
- API documentation: Visit `/` endpoint
- Architecture details: See `README.md` architecture section

## 🆘 Need Help?

1. Check logs: `./deploy.sh logs`
2. Review status: `./deploy.sh info`
3. Verify MQ connectivity
4. Check OpenShift pod status

## 🎉 Success!

You now have a proactive MQ monitoring agent that:
- ✅ Watches your DEADQ 24/7
- 🤖 Analyzes issues with AI
- 💡 Recommends solutions
- 🖥️ Shows everything in real-time
- ✋ Requires your approval for actions

Happy monitoring! 🚀

---

**Made with Bob** 🤖