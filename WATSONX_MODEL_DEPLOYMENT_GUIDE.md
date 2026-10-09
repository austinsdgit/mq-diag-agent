# WatsonX.ai Model Deployment Guide

## Overview
To use AI models in your watsonx.ai deployment space, you need to deploy them first. Here's how:

## Option 1: Deploy via WatsonX.ai UI (Recommended)

### Step 1: Access Prompt Lab
1. Go to https://dataplatform.cloud.ibm.com/
2. Navigate to **AI / Prompt Lab** in the left menu
3. This is where you can test foundation models

### Step 2: Find Available Models
1. In Prompt Lab, click the **Model** dropdown
2. You'll see available foundation models like:
   - `ibm/granite-13b-chat-v2`
   - `meta-llama/llama-3-70b-instruct`
   - `mistralai/mixtral-8x7b-instruct-v01`
3. **Note**: These models can be used directly via API without deployment!

### Step 3: Use Foundation Models Directly
Foundation models in watsonx.ai can be called directly without creating a deployment:

1. Choose a model from Prompt Lab (e.g., `ibm/granite-13b-chat-v2`)
2. Update your MQ Diag Agent config with that exact model ID
3. The model will work immediately via the API

### Alternative: Create a Deployment (Optional)

If you want to create a custom deployment:

1. Go to **Deployments** → Your space
2. Click **Assets** tab
3. Click **New asset** → **Prompt template** or **Tuned foundation model**
4. After creating an asset, you can deploy it
5. Then use the deployment ID in your config

**Note**: For the MQ Diag Agent, using foundation models directly is simpler and doesn't require deployments.

## Option 2: Deploy via API

```bash
# Set your credentials
export WATSONX_API_KEY="Yn9t5yZt_mAW9WHDrA5vMihLuTJhtKpMxNmFfA8up-OU"
export SPACE_ID="2691477a-caef-4e3e-a837-1eb470e1fb1a"

# Get IAM token
IAM_TOKEN=$(curl -X POST 'https://iam.cloud.ibm.com/identity/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=$WATSONX_API_KEY" | jq -r '.access_token')

# Create deployment
curl -X POST 'https://us-south.ml.cloud.ibm.com/ml/v4/deployments?version=2023-05-29' \
  -H "Authorization: Bearer $IAM_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "granite-13b-mq-agent",
    "space_id": "'$SPACE_ID'",
    "asset": {
      "id": "ibm/granite-13b-chat-v2"
    },
    "hardware_spec": {
      "name": "gpu_s",
      "num_nodes": 1
    },
    "online": {}
  }'
```

## Option 3: Use Foundation Models Directly (No Deployment Needed)

Some foundation models can be used directly without deployment:

### Available Foundation Models
- `ibm/granite-13b-chat-v2`
- `meta-llama/llama-3-8b-instruct`
- `mistralai/mistral-large`

### Check Available Models
```bash
curl -X GET 'https://us-south.ml.cloud.ibm.com/ml/v1/foundation_model_specs?version=2023-05-29' \
  -H "Authorization: Bearer $IAM_TOKEN" | jq '.resources[].model_id'
```

## Update MQ Diag Agent Configuration

Once you have a deployed model or know which foundation model to use:

1. Edit `k8s-deployment.yaml`:
```yaml
stringData:
  WATSONX_MODEL_ID: "your-model-id-here"  # e.g., "ibm/granite-13b-chat-v2"
```

2. Redeploy:
```bash
cd mq-diag-agent
oc apply -f k8s-deployment.yaml
oc rollout restart deployment/mq-diag-agent -n mq-diag-agent
```

## Troubleshooting

### Error: "model_not_supported"
- The model isn't deployed in your space
- Try deploying it via the UI first

### Error: "rate_limit_reached"
- You're hitting API limits (2 req/sec)
- The agent now handles this automatically with delays

### Error: "container_not_found"
- Wrong space_id or project_id
- Verify your space ID in watsonx.ai console

## Recommended Models for MQ Agent

1. **IBM Granite 13B Chat** (`ibm/granite-13b-chat-v2`)
   - Best for technical explanations
   - Good balance of speed and quality
   
2. **Meta Llama 3 8B** (`meta-llama/llama-3-8b-instruct`)
   - Faster responses
   - Good for concise explanations

3. **Mistral Large** (`mistralai/mistral-large`)
   - Highest quality
   - Slower and more expensive

## Cost Considerations

- Foundation models: Pay per token
- Deployed models: Pay for compute time
- Lite tier: Limited free usage
- Standard tier: Higher limits, paid

Choose based on your usage patterns and budget.