#!/bin/bash

# Script to delete NONEXISTENTQ queue from QMGRNHA
# This is useful for testing the create_and_replay feature
# The script will clear the queue but NOT delete it, allowing the agent to continue monitoring

echo "Checking if NONEXISTENTQ queue exists..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "echo 'DISPLAY QLOCAL(NONEXISTENTQ)' | runmqsc QMGRNHA" 2>&1 | grep -q "AMQ8147E"

if [ $? -eq 0 ]; then
    echo "✅ Queue NONEXISTENTQ does not exist"
    exit 0
fi

echo "Queue exists. Clearing all messages from NONEXISTENTQ..."
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "echo 'CLEAR QLOCAL(NONEXISTENTQ)' | runmqsc QMGRNHA"

if [ $? -eq 0 ]; then
    echo "✅ Queue NONEXISTENTQ cleared successfully"
    echo ""
    echo "Note: Queue still exists but is empty. This allows you to test the"
    echo "      create_and_replay feature again by sending new test messages."
    echo ""
    echo "      To completely remove the queue, stop the agent first:"
    echo "      oc scale deployment/mq-diag-agent -n mq-diag-agent --replicas=0"
    echo "      Then run: oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c \"echo 'DELETE QLOCAL(NONEXISTENTQ)' | runmqsc QMGRNHA\""
    echo "      Then restart: oc scale deployment/mq-diag-agent -n mq-diag-agent --replicas=1"
else
    echo "⚠️  Failed to clear queue"
fi

echo ""
echo "Current queue status:"
oc exec -n mq-standalone qmgrnha-ibm-mq-0 -- bash -c "echo 'DISPLAY QLOCAL(NONEXISTENTQ) CURDEPTH' | runmqsc QMGRNHA" 2>&1 | grep -E "CURDEPTH|AMQ"

# Made with Bob
