#!/bin/bash
# Test the MQ Diagnostic Agent by putting a message in DEADQ via the agent's API

echo "🧪 Testing MQ Diagnostic Agent"
echo "================================"

# Get the agent pod
POD=$(oc get pod -n mq-diag-agent -l app=mq-diag-agent -o jsonpath='{.items[0].metadata.name}')
echo "📦 Agent Pod: $POD"

# Put a test message in DEADQ using the MCP server inside the pod
echo ""
echo "📨 Putting test message in DEADQ..."
oc exec -n mq-diag-agent $POD -- python3 -c "
import sys
sys.path.insert(0, '/app/ibm-mq-mcp-server/src')
from ibm_mq_mcp.mq_client import MQClient
from ibm_mq_mcp.config import ServerConfig
import os

config = ServerConfig(
    queue_manager=os.getenv('MQ_QUEUE_MANAGER'),
    host=os.getenv('MQ_HOST'),
    port=int(os.getenv('MQ_PORT')),
    channel=os.getenv('MQ_CHANNEL'),
    username=os.getenv('MQ_USERNAME', ''),
    password=os.getenv('MQ_PASSWORD', '')
)

client = MQClient(config)
result = client.put_message(
    queue_name='SYSTEM.DEAD.LETTER.QUEUE',
    message='Test message for DEADQ monitoring - Authorization failure simulation',
    message_type='text'
)
print(f'Result: {result}')
"

echo ""
echo "✅ Test message sent!"
echo ""
echo "🔍 Check the logs for the alert:"
echo "   oc logs -n mq-diag-agent -l app=mq-diag-agent --tail=20 -f"
echo ""
echo "🌐 Or open the UI:"
echo "   https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com"
