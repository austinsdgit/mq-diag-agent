#!/bin/bash

# Setup channels between QMGRNHA and QMGRTEST for testing DEADQ monitoring
# This creates a realistic scenario where messages fail to transmit

set -e

echo "=========================================="
echo "Setting up MQ Channels for DEADQ Testing"
echo "=========================================="

# Get pod names
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
QMGRTEST_POD=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$QMGRNHA_POD" ]; then
    echo "✗ Could not find QMGRNHA pod"
    exit 1
fi

if [ -z "$QMGRTEST_POD" ]; then
    echo "✗ Could not find QMGRTEST pod"
    exit 1
fi

echo "✓ Found QMGRNHA pod: $QMGRNHA_POD"
echo "✓ Found QMGRTEST pod: $QMGRTEST_POD"
echo ""

# Get QMGRTEST service hostname
QMGRTEST_HOST="qmgrtest-ibm-mq.mq-diag-agent.svc.cluster.local"
echo "QMGRTEST service: $QMGRTEST_HOST:1414"
echo ""

# Configure QMGRTEST (receiver side)
echo "Configuring QMGRTEST (receiver)..."
cat > /tmp/qmgrtest-channels.mqsc << EOF
* Create receiver channel from QMGRNHA
DEFINE CHANNEL(TO.QMGRTEST) CHLTYPE(RCVR) TRPTYPE(TCP) REPLACE

* Create target queue
DEFINE QLOCAL(TARGET.QUEUE) REPLACE

* Display configuration
DISPLAY CHANNEL(TO.QMGRTEST)
DISPLAY QLOCAL(TARGET.QUEUE)
EOF

oc cp /tmp/qmgrtest-channels.mqsc mq-diag-agent/$QMGRTEST_POD:/tmp/qmgrtest-channels.mqsc
oc exec -n mq-diag-agent $QMGRTEST_POD -- bash -c "cat /tmp/qmgrtest-channels.mqsc | runmqsc QMGRTEST"
echo "✓ QMGRTEST configured"
echo ""

# Configure QMGRNHA (sender side)
echo "Configuring QMGRNHA (sender)..."
cat > /tmp/qmgrnha-channels.mqsc << EOF
* Create transmission queue
DEFINE QLOCAL(TO.QMGRTEST.XMIT) USAGE(XMITQ) REPLACE

* Create sender channel to QMGRTEST
DEFINE CHANNEL(TO.QMGRTEST) CHLTYPE(SDR) CONNAME('$QMGRTEST_HOST(1414)') XMITQ(TO.QMGRTEST.XMIT) REPLACE

* Create remote queue definition
DEFINE QREMOTE(REMOTE.TARGET.QUEUE) RNAME('TARGET.QUEUE') RQMNAME('QMGRTEST') XMITQ(TO.QMGRTEST.XMIT) REPLACE

* Grant permissions to mqagent
SET AUTHREC PROFILE(TO.QMGRTEST.XMIT) OBJTYPE(QUEUE) PRINCIPAL('mqagent') AUTHADD(PUT,GET,BROWSE,INQ,DSP)
SET AUTHREC PROFILE(TO.QMGRTEST) OBJTYPE(CHANNEL) PRINCIPAL('mqagent') AUTHADD(DSP,CTRL)
SET AUTHREC PROFILE(REMOTE.TARGET.QUEUE) OBJTYPE(QUEUE) PRINCIPAL('mqagent') AUTHADD(PUT,INQ,DSP)

* Start the sender channel
START CHANNEL(TO.QMGRTEST)

* Display configuration
DISPLAY CHANNEL(TO.QMGRTEST)
DISPLAY QLOCAL(TO.QMGRTEST.XMIT)
DISPLAY QREMOTE(REMOTE.TARGET.QUEUE)
DISPLAY CHSTATUS(TO.QMGRTEST)
EOF

oc cp /tmp/qmgrnha-channels.mqsc mq-standalone/$QMGRNHA_POD:/tmp/qmgrnha-channels.mqsc
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c "cat /tmp/qmgrnha-channels.mqsc | runmqsc QMGRNHA"
echo "✓ QMGRNHA configured"
echo ""

# Clean up temp files
rm -f /tmp/qmgrtest-channels.mqsc /tmp/qmgrnha-channels.mqsc

echo "=========================================="
echo "Channel Configuration Complete!"
echo "=========================================="
echo ""
echo "Architecture:"
echo "  QMGRNHA (sender) --> TO.QMGRTEST channel --> QMGRTEST (receiver)"
echo ""
echo "Test Setup:"
echo "  1. QMGRNHA has REMOTE.TARGET.QUEUE pointing to QMGRTEST"
echo "  2. Messages sent to REMOTE.TARGET.QUEUE will transmit to QMGRTEST"
echo "  3. If QMGRTEST is stopped, messages will go to QMGRNHA's DEADQ"
echo "  4. The diagnostic agent will detect them"
echo ""
echo "To test:"
echo "  1. Stop QMGRTEST: oc scale qmgr qmgrtest -n mq-diag-agent --replicas=0"
echo "  2. Send message: ./send-test-message.sh REMOTE.TARGET.QUEUE"
echo "  3. Message will fail and go to DEADQ on QMGRNHA"
echo "  4. Agent will detect and alert"
echo ""
echo "To restore:"
echo "  oc scale qmgr qmgrtest -n mq-diag-agent --replicas=1"
echo ""

# Made with Bob