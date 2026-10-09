# Test Queue Manager for MQ Diagnostic Agent

This directory contains configuration and scripts to deploy a standalone test queue manager (QMGRTEST) for testing the MQ diagnostic agent's DEADQ monitoring capabilities.

## Overview

The test queue manager is configured with:
- **DEADQ**: Dead letter queue for failed messages
- **TEST.REMOTE.QUEUE**: Remote queue definition pointing to a non-existent queue manager
- **TEST.TO.REMOTE**: Sender channel configured to connect to a non-existent host
- **TEST.XMIT.QUEUE**: Transmission queue for the sender channel

When messages are sent to `TEST.REMOTE.QUEUE`, they will fail to transmit and automatically go to `DEADQ`, triggering the diagnostic agent to detect and analyze them.

## Files

- **qmgr-test.yaml**: QueueManager custom resource definition
- **qmgr-test-mqsc-config.yaml**: MQSC configuration with queues, channels, and permissions
- **deploy-test-qmgr.sh**: Automated deployment script
- **test-remote-queue.sh**: Script to send test messages that will fail and go to DEADQ

## Prerequisites

1. OpenShift cluster with IBM MQ operator installed
2. `oc` CLI logged in to the cluster
3. Sufficient permissions to create namespaces and deploy queue managers

## Deployment Steps

### 1. Deploy the Test Queue Manager

```bash
cd mq-diag-agent
./deploy-test-qmgr.sh
```

This script will:
- Create the `mq-diag-agent` namespace (if it doesn't exist)
- Generate a self-signed certificate for the queue manager
- Apply the MQSC configuration
- Deploy the QMGRTEST queue manager
- Wait for the queue manager to be ready (2-3 minutes)

### 2. Verify Deployment

Check the queue manager status:
```bash
oc get qmgr qmgrtest -n mq-diag-agent
```

Expected output:
```
NAME        PHASE     MESSAGE
qmgrtest    Running   
```

### 3. Access the Web Console

Get the web console URL:
```bash
oc get route qmgrtest-ibm-mq-web -n mq-diag-agent -o jsonpath='{.spec.host}'
```

Open the URL in a browser to access the MQ web console.

## Testing DEADQ Monitoring

### Method 1: Send Message to Remote Queue (Recommended)

This method simulates a realistic scenario where messages fail to transmit to a remote queue manager:

```bash
cd mq-diag-agent
./test-remote-queue.sh
```

The script will:
1. Send a persistent message to `TEST.REMOTE.QUEUE`
2. The message will fail to transmit (remote QMGR doesn't exist)
3. MQ will automatically move the message to `DEADQ`
4. The diagnostic agent will detect it within 5 seconds
5. An alert will appear in the diagnostic agent UI

### Method 2: Direct DEADQ Message

Send a message directly to DEADQ:

```bash
cd mq-diag-agent
./send-test-message.sh DEADQ
```

## Monitoring

### Check DEADQ Depth

```bash
POD_NAME=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc exec -n mq-diag-agent $POD_NAME -- bash -c 'echo "DISPLAY QLOCAL(DEADQ) CURDEPTH" | runmqsc QMGRTEST'
```

### View Diagnostic Agent Logs

```bash
oc logs -n mq-diag-agent -l app=mq-diag-agent -f
```

### Access Diagnostic Agent UI

The diagnostic agent UI should be available at:
```
https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com
```

## Queue Manager Configuration

### Queues

- **DEADQ**: Dead letter queue (USAGE=NORMAL)
- **TEST.LOCAL.QUEUE**: Local test queue
- **TEST.REMOTE.QUEUE**: Remote queue definition pointing to non-existent QMGR
- **TEST.XMIT.QUEUE**: Transmission queue (USAGE=XMITQ)

### Channels

- **MQAGENT.SVRCONN**: Server connection channel for the diagnostic agent
- **TEST.TO.REMOTE**: Sender channel configured to connect to `nonexistent.host(1414)`

### Permissions

The `mqagent` user has the following permissions:
- Connect to queue manager
- Browse, get, put messages on DEADQ and TEST.* queues
- Display and control MQAGENT.* and TEST.* channels

## Troubleshooting

### Queue Manager Not Starting

Check the queue manager pod logs:
```bash
POD_NAME=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc logs -n mq-diag-agent $POD_NAME
```

### Messages Not Going to DEADQ

1. Check the sender channel status:
```bash
oc exec -n mq-diag-agent $POD_NAME -- bash -c 'echo "DISPLAY CHSTATUS(TEST.TO.REMOTE)" | runmqsc QMGRTEST'
```

2. Check the transmission queue:
```bash
oc exec -n mq-diag-agent $POD_NAME -- bash -c 'echo "DISPLAY QLOCAL(TEST.XMIT.QUEUE) CURDEPTH" | runmqsc QMGRTEST'
```

### Diagnostic Agent Not Detecting Messages

1. Verify the agent is running:
```bash
oc get pods -n mq-diag-agent -l app=mq-diag-agent
```

2. Check agent configuration:
```bash
oc get configmap mq-diag-agent-config -n mq-diag-agent -o yaml
```

3. Verify the agent is connected to QMGRTEST (not QMGRNHA)

## Cleanup

To remove the test queue manager:

```bash
oc delete qmgr qmgrtest -n mq-diag-agent
oc delete configmap qmgr-test-mqsc-config -n mq-diag-agent
oc delete secret qmgrtest-cert -n mq-diag-agent
```

To remove the entire namespace:
```bash
oc delete namespace mq-diag-agent
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      QMGRTEST                                │
│                                                              │
│  ┌──────────────┐      ┌─────────────────┐                 │
│  │ TEST.REMOTE  │─────▶│ TEST.XMIT.QUEUE │                 │
│  │    QUEUE     │      └─────────────────┘                 │
│  └──────────────┘              │                            │
│                                 │                            │
│                                 ▼                            │
│                      ┌──────────────────┐                   │
│                      │ TEST.TO.REMOTE   │                   │
│                      │ (Sender Channel) │                   │
│                      └──────────────────┘                   │
│                                 │                            │
│                                 │ (Fails - host not found)   │
│                                 ▼                            │
│                         ┌──────────┐                        │
│                         │  DEADQ   │◀────────────────┐      │
│                         └──────────┘                 │      │
│                                 │                    │      │
│                                 │                    │      │
└─────────────────────────────────┼────────────────────┼──────┘
                                  │                    │
                                  │ Browse (every 5s)  │
                                  ▼                    │
                        ┌──────────────────┐           │
                        │  MQ Diag Agent   │           │
                        │   (Monitor)      │───────────┘
                        └──────────────────┘
                                  │
                                  │ WebSocket Alert
                                  ▼
                        ┌──────────────────┐
                        │   Web UI         │
                        │ (Real-time view) │
                        └──────────────────┘
```

## Connection Details

- **Queue Manager**: QMGRTEST
- **Namespace**: mq-diag-agent
- **Service**: qmgrtest-ibm-mq.mq-diag-agent.svc.cluster.local
- **Port**: 1414
- **Channel**: MQAGENT.SVRCONN
- **User**: mqagent

## Made with Bob