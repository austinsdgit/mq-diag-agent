#!/bin/bash
# Send a test message to a queue (will go to DEADQ if queue doesn't exist or has issues)

QUEUE_NAME="${1:-DEADQ}"

echo "🧪 Sending test message to queue: $QUEUE_NAME"
echo "================================"

# Get the agent pod name
POD=$(oc get pod -n mq-diag-agent -l app=mq-diag-agent -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD" ]; then
    echo "❌ Error: No agent pod found"
    exit 1
fi

echo "📦 Using pod: $POD"

# Create Python script to send message
cat > /tmp/send_message.py << EOF
import pymqi
import sys

QUEUE_NAME = "$QUEUE_NAME"

try:
    # Connect to queue manager
    qmgr = pymqi.connect(
        'QMGRNHA',
        'MQAGENT.SVRCONN',
        'qmgrnha-ibm-mq.mq-standalone.svc.cluster.local(1414)'
    )
    
    # Try to open the queue
    try:
        queue = pymqi.Queue(qmgr, QUEUE_NAME, pymqi.CMQC.MQOO_OUTPUT)
        
        # Create message descriptor for persistent message
        md = pymqi.MD()
        md.Persistence = pymqi.CMQC.MQPER_PERSISTENT
        
        # Send test message
        test_message = b'Test message for DEADQ monitoring - sent to ' + QUEUE_NAME.encode()
        queue.put(test_message, md)
        
        print(f'✅ Test message sent to {QUEUE_NAME}')
        print(f'📨 Message: {test_message.decode()}')
        
        # Clean up
        queue.close()
        
    except pymqi.MQMIError as qe:
        print(f'⚠️  Queue error (message will go to DEADQ): {qe}')
        print(f'   Reason: {qe.reason}')
        if qe.reason == 2085:
            print(f'   → Queue {QUEUE_NAME} does not exist')
        elif qe.reason == 2035:
            print(f'   → Not authorized to access {QUEUE_NAME}')
        elif qe.reason == 2004:
            print(f'   → Queue {QUEUE_NAME} is full')
    
    qmgr.disconnect()
    
except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
EOF

# Copy script to pod and execute
echo ""
echo "📨 Sending message..."
oc cp /tmp/send_message.py mq-diag-agent/$POD:/tmp/send_message.py
oc exec -n mq-diag-agent $POD -- python3 /tmp/send_message.py

if [ $? -eq 0 ]; then
    echo ""
    if [ "$QUEUE_NAME" = "SYSTEM.DEAD.LETTER.QUEUE" ]; then
        echo "✅ Message sent directly to DEADQ"
    else
        echo "✅ Message sent (check if it went to DEADQ due to errors) to $QUEUE_NAME"
    fi
    echo ""
    echo "🔍 The agent should detect it within 5 seconds."
    echo "   Check the UI at: https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com"
    echo ""
    echo "📋 Or watch the logs:"
    echo "   oc logs -n mq-diag-agent -l app=mq-diag-agent --tail=20 -f"
else
    echo ""
    echo "❌ Failed to send message"
    exit 1
fi

echo ""
echo "💡 Usage examples:"
echo "   ./send-test-message.sh                    # Send to DEADQ directly"
echo "   ./send-test-message.sh NONEXISTENT.QUEUE  # Will fail and go to DEADQ"
echo "   ./send-test-message.sh APP.QUEUE          # Send to existing queue"

# Made with Bob
