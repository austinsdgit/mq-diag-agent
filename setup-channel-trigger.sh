#!/bin/bash

# Script to configure triggering for TEST.TO.REMOTE channel
# This enables automatic channel startup when messages arrive in XMITQ

set -e

NAMESPACE="mq-diag-agent"
QMGR_NAME="QMGRTEST"
POD_NAME=$(oc get pod -n $NAMESPACE -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
    echo "Error: Could not find Queue Manager pod in namespace $NAMESPACE"
    exit 1
fi

echo "=========================================="
echo "Configuring Channel Triggering"
echo "=========================================="
echo "Queue Manager: $QMGR_NAME"
echo "Pod: $POD_NAME"
echo ""

# Configure triggering on XMITQ
echo "Configuring TEST.XMIT.QUEUE for triggering..."
oc exec -n $NAMESPACE $POD_NAME -- bash -c "cat << 'EOF' | runmqsc $QMGR_NAME
* Enable triggering on transmission queue
ALTER QLOCAL(TEST.XMIT.QUEUE) +
  TRIGGER +
  TRIGTYPE(FIRST) +
  INITQ(SYSTEM.CHANNEL.INITQ) +
  TRIGDATA(TEST.TO.REMOTE)

* Display the updated queue
DISPLAY QLOCAL(TEST.XMIT.QUEUE) TRIGGER TRIGTYPE TRIGDATA INITQ
EOF
"

echo ""
echo "=========================================="
echo "Configuration Complete"
echo "=========================================="
echo ""
echo "Triggering is now enabled:"
echo "- TRIGGER: ON"
echo "- TRIGTYPE: FIRST (trigger on first message)"
echo "- INITQ: SYSTEM.CHANNEL.INITQ"
echo "- TRIGDATA: TEST.TO.REMOTE (channel to start)"
echo ""
echo "The channel will now start automatically when messages"
echo "are put to TEST.XMIT.QUEUE (via TEST.REMOTE.QUEUE)"
echo ""
echo "To test:"
echo "  ./mq-diag-agent/send-multiple-to-nonexistentq.sh 5"
echo ""

# Made with Bob