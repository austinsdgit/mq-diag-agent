#!/bin/bash
set -e

echo "Building and deploying DEADQ forwarder..."

# Build the forwarder image
echo "Building forwarder image..."
oc start-build deadq-forwarder --from-dir=. --follow -n mq-diag-agent

# Deploy the forwarder
echo "Deploying forwarder..."
oc apply -f k8s-forwarder-deployment.yaml

echo "Waiting for forwarder to be ready..."
oc rollout status deployment/deadq-forwarder -n mq-diag-agent --timeout=120s

echo ""
echo "DEADQ Forwarder deployed successfully!"
echo ""
echo "To view forwarder logs:"
echo "  oc logs -f deployment/deadq-forwarder -n mq-diag-agent"
