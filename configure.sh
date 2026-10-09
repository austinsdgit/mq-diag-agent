#!/bin/bash
# Configuration script for MQ Diagnostic Agent

echo "🔧 MQ Diagnostic Agent Configuration"
echo "===================================="
echo ""

# Get Docker Hub username
read -p "Enter your Docker Hub username: " DOCKER_USERNAME

if [ -z "$DOCKER_USERNAME" ]; then
    echo "❌ Docker Hub username is required"
    exit 1
fi

echo ""
echo "📝 Updating configuration files..."

# Update deploy.sh
sed -i.bak "s/your-dockerhub-username/${DOCKER_USERNAME}/g" deploy.sh
echo "✅ Updated deploy.sh"

# Update k8s-deployment.yaml
sed -i.bak "s/your-dockerhub-username/${DOCKER_USERNAME}/g" k8s-deployment.yaml
echo "✅ Updated k8s-deployment.yaml"

# Clean up backup files
rm -f deploy.sh.bak k8s-deployment.yaml.bak

echo ""
echo "✅ Configuration complete!"
echo ""
echo "Your Docker Hub username: ${DOCKER_USERNAME}"
echo "Image will be: ${DOCKER_USERNAME}/mq-diag-agent:latest"
echo ""
echo "Next steps:"
echo "1. Login to Docker Hub: docker login"
echo "2. Build and push: ./deploy.sh build"
echo "3. Deploy: ./deploy.sh deploy"
echo ""

# Made with Bob