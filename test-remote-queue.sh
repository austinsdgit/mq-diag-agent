#!/bin/bash

# Test script to send messages to TEST.REMOTE.QUEUE
# Messages will fail to transmit and go to DEADQ

set -e

NAMESPACE="mq-diag-agent"
QMGR_NAME="QMGRTEST"
QUEUE_NAME="TEST.REMOTE.QUEUE"
POD_NAME=$(oc get pod -n $NAMESPACE -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
    echo "Error: Could not find Queue Manager pod in namespace $NAMESPACE"
    exit 1
fi

echo "=========================================="
echo "Testing DEADQ Monitoring"
echo "=========================================="
echo "Queue Manager: $QMGR_NAME"
echo "Target Queue: $QUEUE_NAME"
echo "Pod: $POD_NAME"
echo ""

# Create Python script to send message
cat > /tmp/send_remote_message.py << 'EOF'
import pymqi
import sys
import os
from datetime import datetime

qmgr_name = os.environ.get('QMGR_NAME', 'QMGRTEST')
queue_name = os.environ.get('QUEUE_NAME', 'TEST.REMOTE.QUEUE')

try:
    # Connect to queue manager
    qmgr = pymqi.connect(qmgr_name)
    print(f"✓ Connected to {qmgr_name}")
    
    # Open queue
    queue = pymqi.Queue(qmgr, queue_name)
    print(f"✓ Opened queue {queue_name}")
    
    # Create test message
    timestamp = datetime.now().isoformat()
    test_message = f"Test message sent at {timestamp} - This will fail and go to DEADQ"
    
    # Set message descriptor for persistent message
    md = pymqi.MD()
    md.Persistence = pymqi.CMQC.MQPER_PERSISTENT
    md.Format = pymqi.CMQC.MQFMT_STRING
    
    # Put message
    queue.put(test_message, md)
    print(f"✓ Message sent to {queue_name}")
    print(f"  Message: {test_message}")
    print(f"  Message ID: {md.MsgId.hex()}")
    
    # Close queue and disconnect
    queue.close()
    qmgr.disconnect()
    
    print("")
    print("Message sent successfully!")
    print("The message will fail to transmit to the remote QMGR")
    print("and should appear in DEADQ within a few seconds.")
    print("")
    print("Check the diagnostic agent UI for the alert:")
    print("https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com")
    
except pymqi.MQMIError as e:
    print(f"✗ MQ Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
EOF

# Copy script to pod and execute
echo "Sending message to $QUEUE_NAME..."
oc cp /tmp/send_remote_message.py $NAMESPACE/$POD_NAME:/tmp/send_remote_message.py

oc exec -n $NAMESPACE $POD_NAME -- bash -c "
export QMGR_NAME=$QMGR_NAME
export QUEUE_NAME=$QUEUE_NAME
python3 /tmp/send_remote_message.py
"

# Clean up
rm -f /tmp/send_remote_message.py

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Wait a few seconds for the message to fail"
echo "2. Check DEADQ: oc exec -n $NAMESPACE $POD_NAME -- bash -c 'echo \"DISPLAY QLOCAL(DEADQ) CURDEPTH\" | runmqsc $QMGR_NAME'"
echo "3. View the diagnostic agent UI for the alert"
echo ""

# Made with Bob