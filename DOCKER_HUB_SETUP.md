# Docker Hub Setup for MQ Diagnostic Agent

## Prerequisites

You need a Docker Hub account to push and pull the agent image.

## Step 1: Create Docker Hub Account

If you don't have one:
1. Go to https://hub.docker.com/
2. Sign up for a free account
3. Verify your email

## Step 2: Login to Docker Hub

```bash
docker login
```

Enter your Docker Hub username and password when prompted.

## Step 3: Configure Your Username

Edit the deployment files with your Docker Hub username:

### Option A: Set Environment Variable (Recommended)

```bash
export DOCKER_USERNAME=your-dockerhub-username
```

### Option B: Edit deploy.sh

Edit `deploy.sh` line 8:
```bash
DOCKER_USERNAME="${DOCKER_USERNAME:-your-dockerhub-username}"
```

Replace `your-dockerhub-username` with your actual username.

### Option C: Edit k8s-deployment.yaml

Edit `k8s-deployment.yaml` line 62:
```yaml
image: your-dockerhub-username/mq-diag-agent:latest
```

Replace `your-dockerhub-username` with your actual username.

## Step 4: Build and Push

```bash
cd mq-diag-agent

# Set your username (if using environment variable)
export DOCKER_USERNAME=your-dockerhub-username

# Build and push
./deploy.sh build
```

This will:
1. Copy IBM MQ MCP Server to build context
2. Build the Docker image
3. Tag it as `your-dockerhub-username/mq-diag-agent:latest`
4. Push to Docker Hub

## Step 5: Deploy to OpenShift

```bash
./deploy.sh deploy
```

OpenShift will pull the image from Docker Hub.

## Troubleshooting

### "unauthorized: authentication required"

You're not logged into Docker Hub:
```bash
docker login
```

### "requested access to the resource is denied"

Either:
1. You're not logged in, or
2. The username in the image name doesn't match your Docker Hub username

### "repository does not exist"

The image hasn't been pushed yet. Run:
```bash
./deploy.sh build
```

## Alternative: Use OpenShift Internal Registry

If you prefer not to use Docker Hub, you can use OpenShift's internal registry:

1. Edit `k8s-deployment.yaml`:
```yaml
image: image-registry.openshift-image-registry.svc:5000/mq-diag-agent/mq-diag-agent:latest
```

2. Build and push to OpenShift registry:
```bash
# Login to OpenShift registry
oc registry login

# Build
docker build -t mq-diag-agent:latest .

# Tag for OpenShift
docker tag mq-diag-agent:latest image-registry.openshift-image-registry.svc:5000/mq-diag-agent/mq-diag-agent:latest

# Push
docker push image-registry.openshift-image-registry.svc:5000/mq-diag-agent/mq-diag-agent:latest
```

## Quick Reference

```bash
# Login to Docker Hub
docker login

# Set username
export DOCKER_USERNAME=your-dockerhub-username

# Build and push
cd mq-diag-agent
./deploy.sh build

# Deploy
./deploy.sh deploy

# Get info
./deploy.sh info
```

---

**Made with Bob** 🤖