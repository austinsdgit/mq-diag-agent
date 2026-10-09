#!/bin/bash
# Setup MQ configuration to naturally route failed messages to DEADQ

echo "🔧 Setting up MQ for realistic DEADQ testing"
echo "=============================================="

# Create MQSC commands
cat > /tmp/setup_deadq_test.mqsc << 'EOF'
* Create a local queue for testing
DEFINE QLOCAL(TEST.SOURCE.QUEUE) +
  REPLACE +
  MAXDEPTH(5000) +
  MAXMSGL(4194304) +
  DEFPSIST(YES) +
  DESCR('Source queue for DEADQ testing')

* Create a remote queue definition pointing to non-existent queue
* This will cause messages to go to DEADQ
DEFINE QREMOTE(TEST.REMOTE.FAIL) +
  REPLACE +
  RNAME(NONEXISTENT.TARGET) +
  RQMNAME(QMGRNHA) +
  XMITQ(TEST.SOURCE.QUEUE) +
  DESCR('Remote queue that will fail and send to DEADQ')

* Create transmission queue
DEFINE QLOCAL(TEST.XMIT.QUEUE) +
  REPLACE +
  USAGE(XMITQ) +
  MAXDEPTH(5000) +
  MAXMSGL(4194304) +
  DEFPSIST(YES) +
  TRIGGER +
  TRIGTYPE(FIRST) +
  TRIGDATA(QMGRNHA) +
  INITQ(SYSTEM.CHANNEL.INITQ) +
  PROCESS(SYSTEM.DEFAULT.PROCESS) +
  DESCR('Transmission queue for testing')

* Create sender channel
DEFINE CHANNEL(TEST.TO.DEADQ) +
  CHLTYPE(SDR) +
  REPLACE +
  CONNAME('localhost(1414)') +
  XMITQ(TEST.XMIT.QUEUE) +
  DESCR('Sender channel for DEADQ testing')

* Start the channel
START CHANNEL(TEST.TO.DEADQ)

* Display configuration
DISPLAY QLOCAL(TEST.SOURCE.QUEUE)
DISPLAY QREMOTE(TEST.REMOTE.FAIL)
DISPLAY QLOCAL(TEST.XMIT.QUEUE)
DISPLAY CHANNEL(TEST.TO.DEADQ)
EOF

echo ""
echo "📝 Applying MQSC configuration..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "cat > /tmp/setup.mqsc << 'EOFMQSC'
$(cat /tmp/setup_deadq_test.mqsc)
EOFMQSC
runmqsc QMGRNHA < /tmp/setup.mqsc"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ MQ configuration complete!"
    echo ""
    echo "📋 Test Configuration Created:"
    echo "   - TEST.SOURCE.QUEUE: Local queue for initial messages"
    echo "   - TEST.REMOTE.FAIL: Remote queue pointing to non-existent target"
    echo "   - TEST.XMIT.QUEUE: Transmission queue"
    echo "   - TEST.TO.DEADQ: Sender channel (will fail and use DEADQ)"
    echo ""
    echo "🧪 To test, send a message to TEST.REMOTE.FAIL:"
    echo "   ./send-test-message.sh TEST.REMOTE.FAIL"
    echo ""
    echo "   The channel will try to deliver it, fail, and move it to DEADQ"
    echo "   The diagnostic agent will then detect and analyze it!"
else
    echo ""
    echo "❌ Configuration failed"
    exit 1
fi

# Made with Bob
