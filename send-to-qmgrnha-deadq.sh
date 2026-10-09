#!/bin/bash
# Send test messages directly to QMGRNHA DEADQ to test the monitoring agent

echo "Sending test messages to QMGRNHA DEADQ..."

QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

# Put 3 test messages directly to DEADQ
for i in 1 2 3; do
  oc exec -n mq-standalone $QMGRNHA_POD -- bash -c "
    echo 'Test message $i - simulating a failed message' | /opt/mqm/samp/bin/amqsput DEADQ QMGRNHA
  "
  echo "Sent message $i"
done

echo ""
echo "Checking DEADQ depth..."
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "DISPLAY QLOCAL(DEADQ) CURDEPTH" | runmqsc QMGRNHA' | grep CURDEPTH

echo ""
echo "Messages sent! The agent should detect them within 10 seconds."
echo "Check the agent logs:"
echo "  oc logs -f deployment/mq-diag-agent -n mq-diag-agent"
echo ""
echo "Or open the UI:"
echo "  https://$(oc get route mq-diag-agent -n mq-diag-agent -o jsonpath='{.spec.host}')"

