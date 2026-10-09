#!/bin/bash
# Run the forwarder once to move messages from QMGRTEST DEADQ to QMGRNHA DEADQ

echo "Running DEADQ forwarder (one-time execution)..."

# Get the mq-diag-agent pod (it has pymqi installed)
AGENT_POD=$(oc get pod -n mq-diag-agent -l app=mq-diag-agent -o jsonpath='{.items[0].metadata.name}')

if [ -z "$AGENT_POD" ]; then
    echo "Error: Could not find mq-diag-agent pod"
    exit 1
fi

echo "Using agent pod: $AGENT_POD"

# Copy the forwarder script to the pod
oc cp deadq-forwarder.py mq-diag-agent/$AGENT_POD:/tmp/deadq-forwarder.py

# Run the forwarder once (not in loop mode)
oc exec -n mq-diag-agent $AGENT_POD -- python3 -c "
import os
import pymqi
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# QMGRTEST connection (source)
SOURCE_QMGR = 'QMGRTEST'
SOURCE_HOST = 'qmgrtest-ibm-mq.mq-diag-agent.svc.cluster.local'
SOURCE_PORT = '1414'
SOURCE_CHANNEL = 'DEV.APP.SVRCONN'
SOURCE_DEADQ = 'DEADQ'

# QMGRNHA connection (destination)
DEST_QMGR = 'QMGRNHA'
DEST_HOST = 'qmgrnha-ibm-mq.mq-standalone.svc.cluster.local'
DEST_PORT = '1414'
DEST_CHANNEL = 'DEV.APP.SVRCONN'
DEST_DEADQ = 'DEADQ'

# Credentials
MQ_USER = os.getenv('IBMMQ_USER', 'app')
MQ_PASSWORD = os.getenv('IBMMQ_PASSWORD')

def connect_qmgr(qmgr_name, host, port, channel):
    conn_info = f'{host}({port})'
    cd = pymqi.CD()
    cd.ChannelName = channel.encode()
    cd.ConnectionName = conn_info.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP
    
    sco = pymqi.SCO()
    qmgr = pymqi.QueueManager(None)
    qmgr.connect_with_options(qmgr_name, cd, sco, user=MQ_USER, password=MQ_PASSWORD)
    return qmgr

logger.info('Connecting to source: ' + SOURCE_QMGR)
source_qmgr = connect_qmgr(SOURCE_QMGR, SOURCE_HOST, SOURCE_PORT, SOURCE_CHANNEL)

logger.info('Connecting to destination: ' + DEST_QMGR)
dest_qmgr = connect_qmgr(DEST_QMGR, DEST_HOST, DEST_PORT, DEST_CHANNEL)

source_queue = pymqi.Queue(source_qmgr, SOURCE_DEADQ, pymqi.CMQC.MQOO_INPUT_AS_Q_DEF)
dest_queue = pymqi.Queue(dest_qmgr, DEST_DEADQ, pymqi.CMQC.MQOO_OUTPUT)

messages_forwarded = 0

while True:
    try:
        md = pymqi.MD()
        gmo = pymqi.GMO()
        gmo.Options = pymqi.CMQC.MQGMO_NO_WAIT | pymqi.CMQC.MQGMO_FAIL_IF_QUIESCING
        
        message = source_queue.get(None, md, gmo)
        
        pmo = pymqi.PMO()
        dest_queue.put(message, md, pmo)
        
        messages_forwarded += 1
        logger.info(f'Forwarded message {messages_forwarded} (MsgId: {md.MsgId.hex()})')
        
    except pymqi.MQMIError as e:
        if e.comp == pymqi.CMQC.MQCC_FAILED and e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
            break
        else:
            raise

logger.info(f'Forwarded {messages_forwarded} messages from {SOURCE_QMGR} to {DEST_QMGR}')

source_queue.close()
dest_queue.close()
source_qmgr.disconnect()
dest_qmgr.disconnect()
"

echo ""
echo "Forwarder execution complete!"
