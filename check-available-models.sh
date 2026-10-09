#!/bin/bash

# Check Available WatsonX.ai Models
# This script queries the watsonx.ai API to see which models are available

set -e

echo "==================================="
echo "WatsonX.ai Available Models Checker"
echo "==================================="
echo ""

# Configuration
WATSONX_API_KEY="Yn9t5yZt_mAW9WHDrA5vMihLuTJhtKpMxNmFfA8up-OU"
WATSONX_SPACE_ID="2691477a-caef-4e3e-a837-1eb470e1fb1a"
WATSONX_URL="https://us-south.ml.cloud.ibm.com"

echo "Step 1: Getting IAM token..."
IAM_TOKEN=$(curl -s -X POST 'https://iam.cloud.ibm.com/identity/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=$WATSONX_API_KEY" | jq -r '.access_token')

if [ -z "$IAM_TOKEN" ] || [ "$IAM_TOKEN" == "null" ]; then
    echo "❌ Failed to get IAM token. Check your API key."
    exit 1
fi

echo "✅ IAM token obtained"
echo ""

echo "Step 2: Checking foundation models..."
echo ""

# Get foundation model specs
MODELS=$(curl -s -X GET "${WATSONX_URL}/ml/v1/foundation_model_specs?version=2023-05-29&filters=function_text_generation" \
  -H "Authorization: Bearer $IAM_TOKEN" \
  -H "Content-Type: application/json")

echo "Available Foundation Models:"
echo "----------------------------"
echo "$MODELS" | jq -r '.resources[] | "- \(.model_id) (\(.label))"' 2>/dev/null || echo "Could not parse models"

echo ""
echo "Step 3: Testing a model with your space_id..."
echo ""

# Try a simple generation with a common model
TEST_MODEL="ibm/granite-13b-chat-v2"
echo "Testing model: $TEST_MODEL"

RESPONSE=$(curl -s -X POST "${WATSONX_URL}/ml/v1/text/generation?version=2023-05-29" \
  -H "Authorization: Bearer $IAM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello",
    "model_id": "'$TEST_MODEL'",
    "space_id": "'$WATSONX_SPACE_ID'",
    "parameters": {
      "max_new_tokens": 10
    }
  }')

if echo "$RESPONSE" | jq -e '.results[0].generated_text' > /dev/null 2>&1; then
    echo "✅ Model $TEST_MODEL works!"
    echo "   Response: $(echo "$RESPONSE" | jq -r '.results[0].generated_text')"
else
    echo "❌ Model $TEST_MODEL failed"
    echo "   Error: $(echo "$RESPONSE" | jq -r '.errors[0].message' 2>/dev/null || echo "$RESPONSE")"
fi

echo ""
echo "==================================="
echo "Recommendation:"
echo "==================================="
echo ""
echo "Update your k8s-deployment.yaml with a working model ID:"
echo ""
echo "  WATSONX_MODEL_ID: \"<model-id-from-above>\""
echo ""
echo "Then redeploy:"
echo "  cd mq-diag-agent"
echo "  oc apply -f k8s-deployment.yaml"
echo "  oc rollout restart deployment/mq-diag-agent -n mq-diag-agent"
echo ""

# Made with Bob
