#!/bin/bash

# Script to send multiple messages to NONEXISTENTQ via TEST.REMOTE.QUEUE
# Usage: ./send-multiple-to-nonexistentq.sh [count]
# Default: 1 message if count not specified

set -e

NAMESPACE="mq-diag-agent"
QMGR_NAME="QMGRTEST"
QUEUE_NAME="TEST.TO.DEADQ"
MESSAGE_COUNT=${1:-1}  # Default to 1 if not specified

# Validate message count
if ! [[ "$MESSAGE_COUNT" =~ ^[0-9]+$ ]] || [ "$MESSAGE_COUNT" -lt 1 ]; then
    echo "Error: Message count must be a positive integer"
    echo "Usage: $0 [count]"
    exit 1
fi

POD_NAME=$(oc get pod -n $NAMESPACE -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
    echo "Error: Could not find Queue Manager pod in namespace $NAMESPACE"
    exit 1
fi

echo "=========================================="
echo "Sending Messages to NONEXISTENTQ"
echo "=========================================="
echo "Queue Manager: $QMGR_NAME"
echo "Target Queue: $QUEUE_NAME (routes to NONEXISTENTQ on QMGRNHA)"
echo "Message Count: $MESSAGE_COUNT"
echo "Pod: $POD_NAME"
echo ""

# Send messages using amqsput (MQ sample program)
echo "Sending $MESSAGE_COUNT message(s) to $QUEUE_NAME..."
echo ""

sent_count=0
failed_count=0

for i in $(seq 1 $MESSAGE_COUNT); do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    MESSAGE="Test message #$i of $MESSAGE_COUNT sent at $TIMESTAMP - Routes to NONEXISTENTQ"
    
    # Use amqsput to send message
    RESULT=$(oc exec -n $NAMESPACE $POD_NAME -- bash -c "echo '$MESSAGE' | /opt/mqm/samp/bin/amqsput $QUEUE_NAME $QMGR_NAME 2>&1")
    
    if [ $? -eq 0 ]; then
        sent_count=$((sent_count + 1))
        
        if [ $MESSAGE_COUNT -le 10 ]; then
            # Show details for small batches
            echo "  [$i/$MESSAGE_COUNT] Message sent successfully"
        elif [ $((i % 10)) -eq 0 ] || [ $i -eq $MESSAGE_COUNT ]; then
            # Show progress for large batches
            echo "  Progress: $i/$MESSAGE_COUNT messages sent"
        fi
    else
        failed_count=$((failed_count + 1))
        echo "  ✗ Failed to send message $i"
    fi
done

echo ""
echo "========================================"
echo "✓ Successfully sent $sent_count message(s) to $QUEUE_NAME"
if [ $failed_count -gt 0 ]; then
    echo "✗ Failed to send $failed_count message(s)"
fi
echo "========================================"
echo ""
echo "Messages will fail to transmit to NONEXISTENTQ"
echo "and should appear in DEADQ within a few seconds."
echo ""
echo "Check the diagnostic agent UI for alerts:"
echo "https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com"

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Wait a few seconds for messages to fail and go to DEADQ"
echo "2. Check DEADQ depth: oc exec -n $NAMESPACE $POD_NAME -- bash -c 'echo \"DISPLAY QLOCAL(DEADQ) CURDEPTH\" | runmqsc $QMGR_NAME'"
echo "3. Check NONEXISTENTQ depth: oc exec -n $NAMESPACE $POD_NAME -- bash -c 'echo \"DISPLAY QLOCAL(NONEXISTENTQ) CURDEPTH MAXDEPTH\" | runmqsc $QMGR_NAME'"
echo "4. View the diagnostic agent UI for alerts"
echo ""

# Made with Bob