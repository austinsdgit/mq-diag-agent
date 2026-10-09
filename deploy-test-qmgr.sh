#!/bin/bash

# Deploy Test Queue Manager for MQ Diagnostic Agent
# This script creates a standalone test QMGR in the mq-diag-agent namespace

set -e

NAMESPACE="mq-diag-agent"
QMGR_NAME="QMGRTEST"

echo "=========================================="
echo "Deploying Test Queue Manager: $QMGR_NAME"
echo "Namespace: $NAMESPACE"
echo "=========================================="

# Check if namespace exists
if ! oc get namespace $NAMESPACE &> /dev/null; then
    echo "✗ Namespace $NAMESPACE does not exist"
    echo "Creating namespace..."
    oc create namespace $NAMESPACE
    echo "✓ Namespace created"
else
    echo "✓ Namespace $NAMESPACE exists"
fi

# Check if IBM MQ operator is available
echo ""
echo "Checking for IBM MQ operator..."
if ! oc get csv -n openshift-operators | grep ibm-mq &> /dev/null; then
    echo "✗ IBM MQ operator not found in openshift-operators namespace"
    echo "Please install the IBM MQ operator first"
    exit 1
fi
echo "✓ IBM MQ operator is installed"

# Create self-signed certificate for QMGR
echo ""
echo "Creating self-signed certificate for $QMGR_NAME..."
if oc get secret qmgrtest-cert -n $NAMESPACE &> /dev/null; then
    echo "Certificate secret already exists, deleting..."
    oc delete secret qmgrtest-cert -n $NAMESPACE
fi

# Generate certificate
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout /tmp/qmgrtest-tls.key \
    -out /tmp/qmgrtest-tls.crt \
    -days 365 \
    -subj "/CN=qmgrtest-ibm-mq.$NAMESPACE.svc.cluster.local/O=IBM/C=US"

# Create secret
oc create secret tls qmgrtest-cert \
    --cert=/tmp/qmgrtest-tls.crt \
    --key=/tmp/qmgrtest-tls.key \
    -n $NAMESPACE

# Clean up temp files
rm -f /tmp/qmgrtest-tls.key /tmp/qmgrtest-tls.crt

echo "✓ Certificate created"

# Apply MQSC ConfigMap
echo ""
echo "Applying MQSC configuration..."
oc apply -f qmgr-test-mqsc-config.yaml
echo "✓ MQSC ConfigMap applied"

# Apply QueueManager
echo ""
echo "Deploying Queue Manager..."
oc apply -f qmgr-test.yaml
echo "✓ QueueManager resource created"

# Wait for QueueManager to be ready
echo ""
echo "Waiting for Queue Manager to be ready (this may take 2-3 minutes)..."
echo "You can monitor progress with: oc get qmgr qmgrtest -n $NAMESPACE -w"

# Wait up to 5 minutes
TIMEOUT=300
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(oc get qmgr qmgrtest -n $NAMESPACE -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    if [ "$STATUS" == "Running" ]; then
        echo "✓ Queue Manager is running!"
        break
    fi
    echo "  Status: $STATUS (waiting...)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "✗ Timeout waiting for Queue Manager to be ready"
    echo "Check status with: oc get qmgr qmgrtest -n $NAMESPACE"
    exit 1
fi

# Get connection details
echo ""
echo "=========================================="
echo "Queue Manager Deployment Complete!"
echo "=========================================="
echo ""
echo "Queue Manager: $QMGR_NAME"
echo "Namespace: $NAMESPACE"
echo ""
echo "Service: qmgrtest-ibm-mq.$NAMESPACE.svc.cluster.local"
echo "Port: 1414"
echo "Channel: MQAGENT.SVRCONN"
echo ""
echo "Web Console Route:"
oc get route qmgrtest-ibm-mq-web -n $NAMESPACE -o jsonpath='{.spec.host}' 2>/dev/null || echo "  (Route not yet created)"
echo ""
echo ""
echo "Test Queues Created:"
echo "  - DEADQ (Dead Letter Queue)"
echo "  - TEST.LOCAL.QUEUE"
echo "  - TEST.REMOTE.QUEUE (points to non-existent QMGR)"
echo "  - TEST.XMIT.QUEUE (transmission queue)"
echo ""
echo "Test Channel:"
echo "  - TEST.TO.REMOTE (sender channel to non-existent host)"
echo ""
echo "To test DEADQ monitoring:"
echo "  1. Put a message to TEST.REMOTE.QUEUE"
echo "  2. The message will fail to transmit and go to DEADQ"
echo "  3. The diagnostic agent will detect and alert"
echo ""
echo "=========================================="

# Made with Bob