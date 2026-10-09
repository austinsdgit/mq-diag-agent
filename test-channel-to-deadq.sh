#!/bin/bash
# Test script to send a message from QMGRTEST to QMGRNHA that will end up in DEADQ
# This simulates a realistic scenario where a message fails to be delivered

# Don't exit on error - some objects may already exist
set +e

echo "=== MQ Diagnostic Agent - Channel Test to DEADQ ==="
echo ""

# Step 1: Configure QMGRTEST with channel to QMGRNHA
echo "Step 1: Configuring QMGRTEST channels..."
oc exec -n mq-diag-agent qmgrtest-ibm-mq-0 -- bash -c "cat > /tmp/setup-channels.mqsc << 'MQSC'
* Define sender channel to QMGRNHA
DEFINE CHANNEL(TO.QMGRNHA) CHLTYPE(SDR) CONNAME('qmgrnha-ibm-mq.mq-standalone.svc.cluster.local(1414)') XMITQ(QMGRNHA.XMIT) TRPTYPE(TCP)

* Define receiver channel from QMGRNHA
DEFINE CHANNEL(FROM.QMGRNHA) CHLTYPE(RCVR) TRPTYPE(TCP)

* Define transmission queue
DEFINE QLOCAL(QMGRNHA.XMIT) USAGE(XMITQ) TRIGGER TRIGTYPE(FIRST) INITQ(SYSTEM.CHANNEL.INITQ) TRIGDATA(TO.QMGRNHA)

* Define remote queue that points to a non-existent queue on QMGRNHA (will cause DEADQ)
DEFINE QREMOTE(TEST.TO.DEADQ) RNAME(NONEXISTENT.QUEUE) RQMNAME(QMGRNHA) XMITQ(QMGRNHA.XMIT)

* Start the sender channel
START CHANNEL(TO.QMGRNHA)
MQSC
runmqsc QMGRTEST < /tmp/setup-channels.mqsc"

echo ""
echo "Step 2: Configuring QMGRNHA receiver channel..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "cat > /tmp/setup-receiver.mqsc << 'MQSC'
* Define receiver channel from QMGRTEST
DEFINE CHANNEL(FROM.QMGRTEST) CHLTYPE(RCVR) TRPTYPE(TCP)

* Define sender channel to QMGRTEST
DEFINE CHANNEL(TO.QMGRTEST) CHLTYPE(SDR) CONNAME('qmgrtest-ibm-mq.mq-diag-agent.svc.cluster.local(1414)') XMITQ(QMGRTEST.XMIT) TRPTYPE(TCP)

* Define transmission queue for replies
DEFINE QLOCAL(QMGRTEST.XMIT) USAGE(XMITQ) TRIGGER TRIGTYPE(FIRST) INITQ(SYSTEM.CHANNEL.INITQ) TRIGDATA(TO.QMGRTEST)
MQSC
runmqsc QMGRNHA < /tmp/setup-receiver.mqsc"

echo ""
echo "Step 3: Waiting for channels to connect..."
sleep 5

echo ""
echo "Step 4: Checking channel status..."
oc exec -n mq-diag-agent qmgrtest-ibm-mq-0 -- bash -c "echo 'DISPLAY CHSTATUS(TO.QMGRNHA)' | runmqsc QMGRTEST" | grep -E "(CHANNEL|STATUS)"

echo ""
echo "Step 5: Sending test message to remote queue (will fail and go to DEADQ)..."
oc exec -n mq-diag-agent qmgrtest-ibm-mq-0 -- bash -c "echo 'Test message from QMGRTEST - should route to DEADQ on QMGRNHA because target queue does not exist' | /opt/mqm/samp/bin/amqsput TEST.TO.DEADQ QMGRTEST"

echo ""
echo "Step 6: Waiting for message to be transmitted and fail..."
sleep 10

echo ""
echo "Step 7: Checking DEADQ on QMGRNHA..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "echo 'DISPLAY QSTATUS(DEADQ) CURDEPTH' | runmqsc QMGRNHA" | grep -E "(QUEUE|CURDEPTH)"

echo ""
echo "Step 8: Checking agent logs for new alert..."
NEW_POD=$(oc get pod -n mq-diag-agent -l app=mq-diag-agent --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
oc logs -n mq-diag-agent $NEW_POD | grep -E "(New message|Alert sent|message\(s\) in DEADQ)" | tail -10

echo ""
echo "=== Test Complete ==="
echo "Check the UI at: https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com"
echo "You should see a new alert for the message that failed to deliver!"

# Made with Bob
