#!/usr/bin/env python3
"""
Test script to put a message in the DEADQ to trigger the diagnostic agent.
"""
import pymqi
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MQ Connection details
qmgr_name = os.getenv('MQ_QUEUE_MANAGER', 'QMGRNHA')
host = os.getenv('MQ_HOST', 'qmgrnha-ibm-mq.mq-standalone.svc.cluster.local')
port = os.getenv('MQ_PORT', '1414')
channel = os.getenv('MQ_CHANNEL', 'MQAGENT.SVRCONN')
deadq_name = os.getenv('MQ_DEADQ', 'SYSTEM.DEAD.LETTER.QUEUE')

# Connection string
conn_info = f"{host}({port})"

print(f"🔌 Connecting to {qmgr_name} at {conn_info}...")

try:
    # Connect to queue manager
    cd = pymqi.CD()
    cd.ChannelName = channel.encode()
    cd.ConnectionName = conn_info.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP

    qmgr = pymqi.connect(qmgr_name, channel, conn_info)
    print(f"✅ Connected to queue manager: {qmgr_name}")

    # Open the DEADQ
    queue = pymqi.Queue(qmgr, deadq_name, pymqi.CMQC.MQOO_OUTPUT)
    print(f"✅ Opened queue: {deadq_name}")

    # Create a test message with a dead letter header
    test_message = "Test message for DEADQ monitoring - simulating authorization failure"
    
    # Put message descriptor
    md = pymqi.MD()
    md.Format = pymqi.CMQC.MQFMT_STRING
    md.Feedback = pymqi.CMQC.MQFB_NONE
    
    # Put the message
    queue.put(test_message.encode())
    print(f"✅ Test message sent to {deadq_name}")
    print(f"📨 Message: {test_message}")
    print(f"\n🔍 Check the UI at: https://mq-diag-agent-mq-diag-agent.apps.itz-oyh4at.tzaas.techzone.ibm.com")
    print(f"⏱️  The agent polls every 5 seconds, so the alert should appear within 5 seconds.")

    # Close queue and disconnect
    queue.close()
    qmgr.disconnect()
    print(f"✅ Disconnected from queue manager")

except pymqi.MQMIError as e:
    print(f"❌ MQ Error: {e}")
    print(f"   Completion Code: {e.comp}")
    print(f"   Reason Code: {e.reason}")
except Exception as e:
    print(f"❌ Error: {e}")

# Made with Bob
