# MQ Diagnostic Agent - Testing Guide

## Overview

The MQ diagnostic agent monitors QMGRNHA's DEADQ and provides real-time alerts with AI-powered recommendations when messages fail.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         QMGRNHA                                  │
│                                                                  │
│  ┌──────────────────────┐      ┌──────────────────────┐        │
│  │ REMOTE.TARGET.QUEUE  │─────▶│ TO.QMGRTEST.XMIT     │        │
│  │  (Remote Queue Def)  │      │ (Transmission Queue) │        │
│  └──────────────────────┘      └──────────────────────┘        │
│                                           │                      │
│                                           ▼                      │
│                                 ┌──────────────────┐            │
│                                 │  TO.QMGRTEST     │            │
│                                 │ (Sender Channel) │            │
│                                 └──────────────────┘            │
│                                           │                      │
└───────────────────────────────────────────┼──────────────────────┘
                                            │
                                            │ TCP Connection
                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         QMGRTEST                                 │
│                                                                  │
│                                 ┌──────────────────┐            │
│                                 │  TO.QMGRTEST     │            │
│                                 │ (Receiver Channel)│           │
│                                 └──────────────────┘            │
│                                           │                      │
│                                           ▼                      │
│                                 ┌──────────────────┐            │
│                                 │  TARGET.QUEUE    │            │
│                                 │  (Local Queue)   │            │
│                                 └──────────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

                    When QMGRTEST is stopped or unreachable:
                    
┌─────────────────────────────────────────────────────────────────┐
│                         QMGRNHA                                  │
│                                                                  │
│                    Failed messages go to:                        │
│                                                                  │
│                         ┌──────────┐                            │
│                         │  DEADQ   │◀─────────────┐             │
│                         └──────────┘              │             │
│                               │                   │             │
│                               │                   │             │
└───────────────────────────────┼───────────────────┼─────────────┘
                                │                   │
                                │ Browse (every 5s) │
                                ▼                   │
                      ┌──────────────────┐          │
                      │  MQ Diag Agent   │──────────┘
                      │   (Monitor)      │
                      └──────────────────┘
                                │
                                │ WebSocket Alert
                                ▼
                      ┌──────────────────┐
                      │   Web UI         │
                      │ (Real-time view) │
                      └──────────────────┘
```

## Prerequisites

1. QMGRNHA is running in mq-standalone namespace
2. QMGRTEST is running in mq-diag-agent namespace
3. Channels are configured (run `./setup-qmgr-channels.sh` if not done)
4. Diagnostic agent is deployed and monitoring QMGRNHA

## Test Scenario 1: Stop QMGRTEST (Recommended)

This simulates a realistic scenario where a remote queue manager becomes unavailable.

### Step 1: Verify Initial State

Check that both queue managers are running:
```bash
oc get qmgr -A
```

Expected output:
```
NAMESPACE        NAME        PHASE     MESSAGE
mq-standalone    qmgrnha     Running   
mq-diag-agent    qmgrtest    Running   
```

### Step 2: Open the Diagnostic Agent UI

Open in your browser:
```
https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com
```

You should see:
- "Connected to WebSocket" status
- "No messages in DEADQ" message

### Step 3: Stop QMGRTEST

```bash
oc scale qmgr qmgrtest -n mq-diag-agent --replicas=0
```

Wait for the pod to terminate:
```bash
oc get pods -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -w
```

### Step 4: Send a Test Message

```bash
cd mq-diag-agent
./send-test-message.sh REMOTE.TARGET.QUEUE
```

This sends a message to REMOTE.TARGET.QUEUE, which points to QMGRTEST. Since QMGRTEST is down, the message will fail to transmit and go to DEADQ.

### Step 5: Observe the Alert

Within 5 seconds, you should see in the UI:
- Real-time alert with message details
- AI-recommended action (e.g., "Check channel status and restart if needed")
- Buttons to approve actions: Delete, Replay, or Investigate

### Step 6: Check DEADQ

Verify the message is in DEADQ:
```bash
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "DISPLAY QLOCAL(DEADQ) CURDEPTH" | runmqsc QMGRNHA'
```

Expected: CURDEPTH should be > 0

### Step 7: Restore QMGRTEST

```bash
oc scale qmgr qmgrtest -n mq-diag-agent --replicas=1
```

Wait for it to be ready:
```bash
oc get qmgr qmgrtest -n mq-diag-agent -w
```

### Step 8: Test Replay Action

In the UI, click "Approve" on the "Replay" action to attempt to resend the message now that QMGRTEST is back online.

## Test Scenario 2: Direct DEADQ Message

This is a simpler test that directly puts a message into DEADQ.

### Step 1: Send Message Directly to DEADQ

```bash
cd mq-diag-agent
./send-test-message.sh DEADQ
```

### Step 2: Observe the Alert

The diagnostic agent will detect the message within 5 seconds and display an alert in the UI.

## Monitoring and Troubleshooting

### Check Agent Logs

```bash
oc logs -n mq-diag-agent -l app=mq-diag-agent -f
```

Look for:
- "Connected to QMGRNHA" - Agent successfully connected
- "Checking DEADQ..." - Monitoring is active
- "Found X messages in DEADQ" - Messages detected

### Check Channel Status

On QMGRNHA:
```bash
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "DISPLAY CHSTATUS(TO.QMGRTEST)" | runmqsc QMGRNHA'
```

Expected statuses:
- RUNNING - Channel is active and transmitting
- RETRYING - Channel is trying to reconnect (QMGRTEST is down)
- STOPPED - Channel has stopped

### Check Transmission Queue

```bash
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "DISPLAY QLOCAL(TO.QMGRTEST.XMIT) CURDEPTH" | runmqsc QMGRNHA'
```

If CURDEPTH > 0, messages are waiting to be transmitted.

### Restart Sender Channel

If the channel doesn't automatically restart:
```bash
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "START CHANNEL(TO.QMGRTEST)" | runmqsc QMGRNHA'
```

## Understanding the Alerts

### Alert Components

Each alert shows:
1. **Message ID**: Unique identifier for the message
2. **Timestamp**: When the message was detected
3. **Reason Code**: MQ reason code (e.g., 2009 = connection broken)
4. **Message Content**: Preview of the message payload
5. **AI Recommendation**: Suggested action based on the reason code

### Common Reason Codes

- **2009 (MQRC_CONNECTION_BROKEN)**: Remote queue manager is unavailable
- **2035 (MQRC_NOT_AUTHORIZED)**: Authorization failure
- **2085 (MQRC_UNKNOWN_OBJECT_NAME)**: Queue or channel doesn't exist
- **2003 (MQRC_HOBJ_ERROR)**: Object handle error
- **2004 (MQRC_OBJECT_CHANGED)**: Object definition changed

### Actions

- **Delete**: Remove the message from DEADQ (use for invalid/test messages)
- **Replay**: Attempt to resend the message to its original destination
- **Investigate**: Mark for manual investigation (logs the issue)

## Advanced Testing

### Test Multiple Messages

Send multiple messages in quick succession:
```bash
for i in {1..5}; do
  ./send-test-message.sh REMOTE.TARGET.QUEUE
  sleep 1
done
```

The agent will detect all messages and show them in the UI.

### Test Different Failure Scenarios

1. **Authorization Failure**: Modify channel MCAUSER to invalid user
2. **Queue Full**: Set MAXDEPTH on TARGET.QUEUE to a low value
3. **Network Issue**: Use firewall rules to block traffic between QMGRs

## Cleanup

### Clear DEADQ

```bash
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "CLEAR QLOCAL(DEADQ)" | runmqsc QMGRNHA'
```

### Remove Test Configuration

```bash
# On QMGRNHA
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'cat <<EOF | runmqsc QMGRNHA
DELETE QREMOTE(REMOTE.TARGET.QUEUE)
STOP CHANNEL(TO.QMGRTEST)
DELETE CHANNEL(TO.QMGRTEST)
DELETE QLOCAL(TO.QMGRTEST.XMIT)
EOF'

# On QMGRTEST
QMGRTEST_POD=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
oc exec -n mq-diag-agent $QMGRTEST_POD -- bash -c 'cat <<EOF | runmqsc QMGRTEST
DELETE CHANNEL(TO.QMGRTEST)
DELETE QLOCAL(TARGET.QUEUE)
EOF'
```

## Success Criteria

✅ Agent connects to QMGRNHA successfully  
✅ Agent detects messages in DEADQ within 5 seconds  
✅ UI displays real-time alerts via WebSocket  
✅ AI recommendations are relevant to the failure reason  
✅ Actions (Delete/Replay/Investigate) work correctly  
✅ No duplicate alerts for the same message  
✅ Messages remain in DEADQ after browsing (non-destructive)  

## Made with Bob