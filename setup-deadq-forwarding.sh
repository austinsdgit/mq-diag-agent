#!/bin/bash

# This script configures QMGRTEST to forward DEADQ messages to QMGRNHA
# When messages fail on QMGRTEST, they go to local DEADQ, then get forwarded to QMGRNHA's DEADQ

echo "Configuring DEADQ forwarding from QMGRTEST to QMGRNHA..."

# Get the QMGRTEST pod
QMGRTEST_POD=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$QMGRTEST_POD" ]; then
    echo "Error: Could not find QMGRTEST pod"
    exit 1
fi

echo "Found QMGRTEST pod: $QMGRTEST_POD"

# Configure QMGRTEST to forward DEADQ messages to QMGRNHA
oc exec -n mq-diag-agent $QMGRTEST_POD -- bash -c 'cat <<MQSC | runmqsc QMGRTEST

* Define transmission queue to QMGRNHA
DEFINE QLOCAL(TO.QMGRNHA.XMIT) +
  USAGE(XMITQ) +
  REPLACE

* Define sender channel to QMGRNHA
DEFINE CHANNEL(TO.QMGRNHA) +
  CHLTYPE(SDR) +
  CONNAME("qmgrnha-ibm-mq.mq-standalone.svc.cluster.local(1414)") +
  XMITQ(TO.QMGRNHA.XMIT) +
  TRPTYPE(TCP) +
  REPLACE

* Define remote queue pointing to QMGRNHA DEADQ
DEFINE QREMOTE(QMGRNHA.DEADQ) +
  RNAME(DEADQ) +
  RQMNAME(QMGRNHA) +
  XMITQ(TO.QMGRNHA.XMIT) +
  REPLACE

* Start the sender channel
START CHANNEL(TO.QMGRNHA)

MQSC
'

echo ""
echo "Now configuring QMGRNHA to receive from QMGRTEST..."

# Get the QMGRNHA pod
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

if [ -z "$QMGRNHA_POD" ]; then
    echo "Error: Could not find QMGRNHA pod"
    exit 1
fi

echo "Found QMGRNHA pod: $QMGRNHA_POD"

# Configure QMGRNHA to receive from QMGRTEST
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'cat <<MQSC | runmqsc QMGRNHA

* Define receiver channel from QMGRTEST
DEFINE CHANNEL(TO.QMGRNHA) +
  CHLTYPE(RCVR) +
  TRPTYPE(TCP) +
  REPLACE

* Start the receiver channel (will auto-start when sender connects)
START CHANNEL(TO.QMGRNHA)

MQSC
'

echo ""
echo "Configuration complete!"
echo ""
echo "To test the forwarding, we need to create a process that moves messages from QMGRTEST DEADQ to QMGRNHA.DEADQ"
echo "This requires a small application or trigger on QMGRTEST's DEADQ"

