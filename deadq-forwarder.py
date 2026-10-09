#!/usr/bin/env python3
"""
DEADQ Forwarder - Moves messages from QMGRTEST DEADQ to QMGRNHA DEADQ
This runs as a simple service that periodically checks QMGRTEST's DEADQ
and forwards any messages to QMGRNHA's DEADQ.
"""
import os
import time
import pymqi
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# QMGRTEST connection (source)
SOURCE_QMGR = "QMGRTEST"
SOURCE_HOST = "qmgrtest-ibm-mq.mq-diag-agent.svc.cluster.local"
SOURCE_PORT = "1414"
SOURCE_CHANNEL = "DEV.APP.SVRCONN"
SOURCE_DEADQ = "DEADQ"

# QMGRNHA connection (destination)
DEST_QMGR = "QMGRNHA"
DEST_HOST = "qmgrnha-ibm-mq.mq-standalone.svc.cluster.local"
DEST_PORT = "1414"
DEST_CHANNEL = "DEV.APP.SVRCONN"
DEST_DEADQ = "DEADQ"

# Credentials (same for both)
MQ_USER = os.getenv("IBMMQ_USER", "app")
MQ_PASSWORD = os.getenv("IBMMQ_PASSWORD")

CHECK_INTERVAL = 10  # seconds

def connect_qmgr(qmgr_name, host, port, channel):
    """Connect to a queue manager"""
    conn_info = f"{host}({port})"
    cd = pymqi.CD()
    cd.ChannelName = channel.encode()
    cd.ConnectionName = conn_info.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP
    
    sco = pymqi.SCO()
    qmgr = pymqi.QueueManager(None)
    qmgr.connect_with_options(qmgr_name, cd, sco, user=MQ_USER, password=MQ_PASSWORD)
    return qmgr

def forward_messages():
    """Forward messages from source DEADQ to destination DEADQ"""
    source_qmgr = None
    dest_qmgr = None
    
    try:
        # Connect to both queue managers
        logger.info(f"Connecting to source: {SOURCE_QMGR}")
        source_qmgr = connect_qmgr(SOURCE_QMGR, SOURCE_HOST, SOURCE_PORT, SOURCE_CHANNEL)
        
        logger.info(f"Connecting to destination: {DEST_QMGR}")
        dest_qmgr = connect_qmgr(DEST_QMGR, DEST_HOST, DEST_PORT, DEST_CHANNEL)
        
        # Open source DEADQ for destructive get
        source_queue = pymqi.Queue(source_qmgr, SOURCE_DEADQ, pymqi.CMQC.MQOO_INPUT_AS_Q_DEF)
        
        # Open destination DEADQ for put
        dest_queue = pymqi.Queue(dest_qmgr, DEST_DEADQ, pymqi.CMQC.MQOO_OUTPUT)
        
        messages_forwarded = 0
        
        while True:
            try:
                # Get message from source
                md = pymqi.MD()
                gmo = pymqi.GMO()
                gmo.Options = pymqi.CMQC.MQGMO_NO_WAIT | pymqi.CMQC.MQGMO_FAIL_IF_QUIESCING
                
                message = source_queue.get(None, md, gmo)
                
                # Put message to destination
                pmo = pymqi.PMO()
                dest_queue.put(message, md, pmo)
                
                messages_forwarded += 1
                logger.info(f"Forwarded message {messages_forwarded} (MsgId: {md.MsgId.hex()})")
                
            except pymqi.MQMIError as e:
                if e.comp == pymqi.CMQC.MQCC_FAILED and e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                    # No more messages
                    break
                else:
                    raise
        
        if messages_forwarded > 0:
            logger.info(f"Forwarded {messages_forwarded} messages from {SOURCE_QMGR} to {DEST_QMGR}")
        
        source_queue.close()
        dest_queue.close()
        
    finally:
        if source_qmgr:
            source_qmgr.disconnect()
        if dest_qmgr:
            dest_qmgr.disconnect()

def main():
    """Main loop"""
    logger.info("DEADQ Forwarder starting...")
    logger.info(f"Source: {SOURCE_QMGR} ({SOURCE_HOST}:{SOURCE_PORT}) - {SOURCE_DEADQ}")
    logger.info(f"Destination: {DEST_QMGR} ({DEST_HOST}:{DEST_PORT}) - {DEST_DEADQ}")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
    
    while True:
        try:
            forward_messages()
        except Exception as e:
            logger.error(f"Error forwarding messages: {e}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
