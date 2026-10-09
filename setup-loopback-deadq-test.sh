#!/bin/bash
# Setup loopback channels on QMGRNHA for realistic DEADQ testing

echo "🔧 Setting up loopback channels for DEADQ testing"
echo "=================================================="

# Create MQSC commands
cat > /tmp/setup_loopback.mqsc << 'EOF'
* Create target queue that doesn't exist (will cause DEADQ)
* We'll reference it but not create it

* Create transmission queue
DEFINE QLOCAL(TEST.XMIT.QUEUE) +
  REPLACE +
  USAGE(XMITQ) +
  MAXDEPTH(5000) +
  MAXMSGL(4194304) +
  DEFPSIST(YES) +
  DESCR('Transmission queue for loopback testing')

* Create sender channel (will send to receiver on same QMGR)
DEFINE CHANNEL(TEST.SENDER) +
  CHLTYPE(SDR) +
  REPLACE +
  CONNAME('localhost(1414)') +
  XMITQ(TEST.XMIT.QUEUE) +
  DESCR('Sender channel for loopback')

* Create receiver channel (receives from sender) - must have same name
DEFINE CHANNEL(TEST.SENDER) +
  CHLTYPE(RCVR) +
  REPLACE

* Create remote queue definition pointing to non-existent queue
* Messages sent here will go through channel and fail
DEFINE QREMOTE(TEST.FAIL.REMOTE) +
  REPLACE +
  RNAME(NONEXISTENT.TARGET.QUEUE) +
  RQMNAME(QMGRNHA) +
  XMITQ(TEST.XMIT.QUEUE) +
  DESCR('Remote queue that will fail - target does not exist')

* Start the sender channel
START CHANNEL(TEST.SENDER)

* Display configuration
DISPLAY QLOCAL(TEST.XMIT.QUEUE)
DISPLAY QREMOTE(TEST.FAIL.REMOTE)
DISPLAY CHANNEL(TEST.SENDER) CHLTYPE(SDR)
DISPLAY CHANNEL(TEST.SENDER) CHLTYPE(RCVR)
EOF

echo ""
echo "📝 Applying MQSC configuration to QMGRNHA..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "cat > /tmp/setup.mqsc << 'EOFMQSC'
$(cat /tmp/setup_loopback.mqsc)
EOFMQSC
runmqsc QMGRNHA < /tmp/setup.mqsc"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Loopback channel configuration complete!"
    echo ""
    echo "📋 Configuration Created:"
    echo "   - TEST.XMIT.QUEUE: Transmission queue"
    echo "   - TEST.SENDER (SDR): Sender channel"
    echo "   - TEST.SENDER (RCVR): Receiver channel (same name, loopback)"
    echo "   - TEST.FAIL.REMOTE: Remote queue → NONEXISTENT.TARGET.QUEUE"
    echo ""
    echo "🧪 How it works:"
    echo "   1. Send message to TEST.FAIL.REMOTE"
    echo "   2. Message goes to TEST.XMIT.QUEUE"
    echo "   3. TEST.SENDER channel picks it up"
    echo "   4. Sends to TEST.SENDER receiver (loopback)"
    echo "   5. Receiver tries to put to NONEXISTENT.TARGET.QUEUE"
    echo "   6. Fails → Message goes to DEADQ"
    echo "   7. Diagnostic agent detects and analyzes it!"
    echo ""
    echo "🚀 To test:"
    echo "   ./send-test-message.sh TEST.FAIL.REMOTE"
    echo ""
    echo "   Then check DEADQ depth:"
    echo "   oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c \"echo 'DISPLAY QUEUE(DEADQ) CURDEPTH' | runmqsc QMGRNHA\""
else
    echo ""
    echo "❌ Configuration failed"
    exit 1
fi

# Made with Bob
