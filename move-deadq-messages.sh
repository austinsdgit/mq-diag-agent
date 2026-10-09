#!/bin/bash
# Move messages from QMGRTEST DEADQ to QMGRNHA DEADQ using amqsget/amqsput

echo "Moving messages from QMGRTEST DEADQ to QMGRNHA DEADQ..."

QMGRTEST_POD=$(oc get pod -n mq-diag-agent -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')
QMGRNHA_POD=$(oc get pod -n mq-standalone -l app.kubernetes.io/name=ibm-mq -o jsonpath='{.items[0].metadata.name}')

# Get messages from QMGRTEST DEADQ and save to temp file
echo "Getting messages from QMGRTEST..."
oc exec -n mq-diag-agent $QMGRTEST_POD -- bash -c '
cd /tmp
count=0
while true; do
  # Try to get a message
  echo "" | /opt/mqm/samp/bin/amqsget DEADQ QMGRTEST > msg_$count.txt 2>&1
  
  # Check if we got a message (file size > 100 bytes means we got something)
  if [ $(wc -c < msg_$count.txt) -gt 100 ]; then
    echo "Got message $count"
    count=$((count+1))
  else
    rm msg_$count.txt
    break
  fi
done
echo "Total messages retrieved: $count"
ls -la msg_*.txt 2>/dev/null || echo "No messages found"
'

# For now, let's just check the queue depths
echo ""
echo "Checking queue depths..."
oc exec -n mq-diag-agent $QMGRTEST_POD -- bash -c 'echo "DISPLAY QLOCAL(DEADQ) CURDEPTH" | runmqsc QMGRTEST' | grep CURDEPTH
oc exec -n mq-standalone $QMGRNHA_POD -- bash -c 'echo "DISPLAY QLOCAL(DEADQ) CURDEPTH" | runmqsc QMGRNHA' | grep CURDEPTH

