#!/bin/bash
# Deployment script for MQ Diagnostic Agent

set -e

echo "🚀 MQ Diagnostic Agent Deployment Script"
echo "========================================"

# Configuration
DOCKER_USERNAME="${DOCKER_USERNAME:-austinsd}"  # Set via environment or edit here
IMAGE_NAME="mq-diag-agent"
IMAGE_TAG="latest"
NAMESPACE="mq-diag-agent"
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# Check if running in OpenShift
if oc version &> /dev/null; then
    echo "✅ OpenShift CLI detected"
    PLATFORM="openshift"
else
    echo "❌ OpenShift CLI not found. Please install 'oc' command."
    exit 1
fi

# Function to build and push image
build_image() {
    echo ""
    echo "📦 Preparing build context..."
    
    # Copy MCP server to build context if it doesn't exist
    if [ ! -d "ibm-mq-mcp-server" ]; then
        if [ -d "../ibm-mq-mcp-server" ]; then
            echo "📋 Copying IBM MQ MCP Server to build context..."
            cp -r ../ibm-mq-mcp-server ./ibm-mq-mcp-server
        else
            echo "❌ IBM MQ MCP Server not found at ../ibm-mq-mcp-server"
            echo "Please ensure ibm-mq-mcp-server exists in the parent directory"
            exit 1
        fi
    fi
    
    echo "📦 Building Docker image..."
    
    # Build the image
    docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .
    
    if [ $? -eq 0 ]; then
        echo "✅ Image built successfully"
    else
        echo "❌ Image build failed"
        exit 1
    fi
    
    # Tag for Docker Hub
    echo "🏷️  Tagging image for Docker Hub..."
    docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${FULL_IMAGE_NAME}
    
    # Check if logged into Docker Hub
    echo "🔐 Checking Docker Hub login..."
    if ! docker info | grep -q "Username"; then
        echo "⚠️  Not logged into Docker Hub. Please login:"
        echo "   docker login"
        echo ""
        read -p "Press Enter after logging in, or Ctrl+C to cancel..."
    fi
    
    # Push to Docker Hub
    echo "📤 Pushing image to Docker Hub..."
    docker push ${FULL_IMAGE_NAME}
    
    if [ $? -eq 0 ]; then
        echo "✅ Image pushed to Docker Hub: ${FULL_IMAGE_NAME}"
    else
        echo "❌ Failed to push image to Docker Hub"
        echo "💡 Make sure you're logged in: docker login"
        exit 1
    fi
}

# Function to deploy to Kubernetes/OpenShift
deploy() {
    echo ""
    echo "🚢 Deploying to ${PLATFORM}..."
    
    # Apply the deployment
    oc apply -f k8s-deployment.yaml
    
    if [ $? -eq 0 ]; then
        echo "✅ Deployment applied successfully"
    else
        echo "❌ Deployment failed"
        exit 1
    fi
    
    # Wait for deployment to be ready
    echo ""
    echo "⏳ Waiting for deployment to be ready..."
    oc wait --for=condition=available --timeout=300s deployment/mq-diag-agent -n ${NAMESPACE}
    
    if [ $? -eq 0 ]; then
        echo "✅ Deployment is ready"
    else
        echo "⚠️  Deployment is taking longer than expected"
    fi
}

# Function to get access information
get_info() {
    echo ""
    echo "📋 Deployment Information"
    echo "========================"
    
    # Get route URL
    ROUTE_URL=$(oc get route mq-diag-agent -n ${NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    
    if [ -n "$ROUTE_URL" ]; then
        echo "🌐 Application URL: https://${ROUTE_URL}"
        echo ""
        echo "📱 Access the UI at: https://${ROUTE_URL}"
        echo "🔌 WebSocket endpoint: wss://${ROUTE_URL}/ws"
        echo "💚 Health check: https://${ROUTE_URL}/health"
    else
        echo "⚠️  Route not found. Creating route..."
        oc expose service mq-diag-agent -n ${NAMESPACE}
        ROUTE_URL=$(oc get route mq-diag-agent -n ${NAMESPACE} -o jsonpath='{.spec.host}')
        echo "🌐 Application URL: https://${ROUTE_URL}"
    fi
    
    echo ""
    echo "📊 Pod Status:"
    oc get pods -n ${NAMESPACE} -l app=mq-diag-agent
    
    echo ""
    echo "📝 To view logs:"
    echo "   oc logs -f deployment/mq-diag-agent -n ${NAMESPACE}"
    
    echo ""
    echo "🔍 To check status:"
    echo "   oc get all -n ${NAMESPACE}"
}

# Main execution
case "${1:-all}" in
    build)
        build_image
        ;;
    deploy)
        deploy
        get_info
        ;;
    all)
        build_image
        deploy
        get_info
        ;;
    info)
        get_info
        ;;
    logs)
        echo "📝 Streaming logs..."
        oc logs -f deployment/mq-diag-agent -n ${NAMESPACE}
        ;;
    delete)
        echo "🗑️  Deleting deployment..."
        oc delete -f k8s-deployment.yaml
        echo "✅ Deployment deleted"
        ;;
    *)
        echo "Usage: $0 {build|deploy|all|info|logs|delete}"
        echo ""
        echo "Commands:"
        echo "  build   - Build Docker image only"
        echo "  deploy  - Deploy to cluster only"
        echo "  all     - Build and deploy (default)"
        echo "  info    - Show deployment information"
        echo "  logs    - Stream application logs"
        echo "  delete  - Delete the deployment"
        exit 1
        ;;
esac

echo ""
echo "✅ Done!"

# Made with Bob