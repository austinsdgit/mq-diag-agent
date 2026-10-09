"""
MQ Diagnostic Agent - DEADQ Monitor
Monitors the dead letter queue and sends proactive alerts with AI recommendations
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import pymqi
import httpx

# Add MCP server to Python path
sys.path.insert(0, '/app/ibm-mq-mcp-server/src')

from ibm_mq_mcp.server import IBMMQMCPServer
from ibm_mq_mcp.config import ServerConfig

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeadQueueMonitor:
    """Monitor the dead letter queue and generate AI recommendations."""
    
    def __init__(self, websocket_handler=None):
        """Initialize the monitor."""
        self.config = ServerConfig()
        self.mcp_server = IBMMQMCPServer()
        self.connected = False
        self.monitoring = False
        self.websocket_handler = websocket_handler
        self.deadq_name = os.getenv("DEADQ_NAME", "SYSTEM.DEAD.LETTER.QUEUE")
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "5"))  # seconds
        self.alerted_messages = set()  # Track message IDs we've already alerted on
        
        # WatsonX AI Configuration
        self.watsonx_api_key = os.getenv("WATSONX_API_KEY")
        self.watsonx_project_id = os.getenv("WATSONX_PROJECT_ID")
        self.watsonx_space_id = os.getenv("WATSONX_SPACE_ID")  # Alternative to project_id
        
        # Queue Capacity Monitoring Configuration
        self.capacity_threshold = int(os.getenv("CAPACITY_THRESHOLD", "80"))  # Default 80%
        self.capacity_poll_interval = int(os.getenv("CAPACITY_POLL_INTERVAL", "10"))  # seconds
        self.capacity_monitoring = False
        self.tracked_queues = {}  # Track queue capacity states
        self.watsonx_url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        
        # Auto-Resolve Configuration
        self.auto_resolve_enabled = False  # Controlled by UI toggle
        self.auto_resolve_rules = {
            2053: True,  # MQRC_Q_FULL - Auto-resolve by increasing MAXDEPTH
            2085: True,  # MQRC_UNKNOWN_OBJECT_NAME - Auto-resolve by creating queue
        }
        self.auto_resolved_messages = set()  # Track auto-resolved message IDs
        self.queues_already_altered = set()  # Track queues altered this session to prevent re-altering
        self.auto_resolve_audit_log = []  # Audit log for auto-resolve actions (max 100 entries)
        self.max_audit_log_entries = 100  # Keep last 100 audit entries
        
    async def initialize(self):
        """Initialize the monitor and connect to MQ."""
        logger.info("Initializing DEADQ Monitor...")
        try:
            # Connect directly to MQ (bypasses MCP authorization)
            result = self.mcp_server.mq_client.connect()
            self.connected = True
            logger.info(f"Connected to MQ: {result}")

            return result
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            raise

    
    def _get_actions_for_message(self, original_queue: str, reason_code: int) -> List[Dict[str, Any]]:
        """
        Get available actions based on the message context.
        
        Args:
            original_queue: The original queue name
            reason_code: The MQ reason code
            
        Returns:
            List of available actions
        """
        actions = [
            {
                "id": "view_details",
                "label": "View Full Message",
                "type": "info"
            }
        ]
        
        # If original queue is Unknown and reason is MQRC_UNKNOWN_OBJECT_NAME, offer to create queue
        if original_queue == "Unknown" or reason_code == 2085:
            actions.append({
                "id": "create_and_replay",
                "label": "Create Queue & Replay Message",
                "type": "action",
                "requires_approval": True
            })
        else:
            actions.append({
                "id": "replay_message",
                "label": "Replay to Original Queue",
                "type": "action",
                "requires_approval": True
            })
        
        # If queue full error (2053 or 2004), offer to increase MAXDEPTH
        if reason_code in [2053, 2004] and original_queue != "Unknown":
            actions.append({
                "id": "increase_maxdepth",
                "label": f"Increase MAXDEPTH on {original_queue}",
                "type": "action",
                "requires_approval": True,
                "queue_name": original_queue
            })
        
        actions.extend([
            {
                "id": "delete_message",
                "label": "Delete Message",
                "type": "action",
                "requires_approval": True
            },
            {
                "id": "investigate",
                "label": "Start Investigation",
                "type": "action",
                "requires_approval": False
            }
        ])
        
        return actions
    
    async def analyze_dead_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a dead letter message and generate recommendations.
        
        Args:
            message_data: Message data from the dead letter queue
            
        Returns:
            Analysis with recommendations
        """
        try:
            logger.info(f"Analyzing message data: {message_data}")
            
            # Extract dead letter header information
            # Note: MCP server may not parse DLH, so we handle both cases
            reason = message_data.get('reason', 0)
            feedback = message_data.get('feedback', 0)
            original_queue = message_data.get('original_queue', 'Unknown')
            message_content = message_data.get('message', '')
            
            # If no reason code, this might be a simple message in DEADQ
            # Treat it as a general issue
            if reason == 0 or reason == 'Unknown':
                reason = 9999  # Custom code for "unknown reason"
                logger.warning(f"No reason code found in message, using default")
            
            # Generate recommendations based on reason code
            recommendations = []
            severity = "medium"
            
            # Common reason codes and recommendations
            reason_code_map = {
                2003: {  # MQRC_MSG_TOO_BIG_FOR_Q
                    "name": "MQRC_MSG_TOO_BIG_FOR_Q",
                    "description": "Message too large for queue",
                    "recommendations": [
                        "Increase MAXMSGL on the queue",
                        "Split large messages into smaller chunks",
                        "Use message segmentation"
                    ],
                    "severity": "high"
                },
                2004: {  # MQRC_Q_FULL
                    "name": "MQRC_Q_FULL",
                    "description": "Queue is full",
                    "recommendations": [
                        "Increase MAXDEPTH on the queue",
                        "Check if consumers are processing messages",
                        "Investigate why messages are accumulating"
                    ],
                    "severity": "high"
                },
                2053: {  # MQRC_Q_FULL (alternate code)
                    "name": "MQRC_Q_FULL",
                    "description": "Queue is full",
                    "recommendations": [
                        "Increase MAXDEPTH on the queue",
                        "Check if consumers are processing messages",
                        "Investigate why messages are accumulating"
                    ],
                    "severity": "high"
                },
                2085: {  # MQRC_UNKNOWN_OBJECT_NAME
                    "name": "MQRC_UNKNOWN_OBJECT_NAME",
                    "description": "Target queue does not exist",
                    "recommendations": [
                        f"Create the queue '{original_queue}'",
                        "Check queue name spelling",
                        "Verify queue manager configuration"
                    ],
                    "severity": "critical"
                },
                2035: {  # MQRC_NOT_AUTHORIZED
                    "name": "MQRC_NOT_AUTHORIZED",
                    "description": "Authorization failure",
                    "recommendations": [
                        "Grant appropriate permissions to the user/application",
                        "Check channel authentication records (CHLAUTH)",
                        "Review security policies"
                    ],
                    "severity": "critical"
                },
                2009: {  # MQRC_CONNECTION_BROKEN
                    "name": "MQRC_CONNECTION_BROKEN",
                    "description": "Connection broken",
                    "recommendations": [
                        "Check network connectivity",
                        "Review channel status",
                        "Investigate application logs for errors"
                    ],
                    "severity": "high"
                },
                9999: {  # Custom: Unknown reason
                    "name": "UNKNOWN",
                    "description": "Message in dead letter queue (reason unknown)",
                    "recommendations": [
                        "Check message descriptor for details",
                        "Review application logs",
                        "Verify queue manager error logs",
                        "Check if message has dead letter header"
                    ],
                    "severity": "medium"
                }
            }
            
            reason_info = reason_code_map.get(reason, {
                "name": f"MQRC_{reason}",
                "description": f"Reason code: {reason}",
                "recommendations": [
                    "Check application and queue manager logs",
                    "Contact support if issue persists"
                ],
                "severity": "medium"
            })
            
            # Get AI-generated explanation for the reason code
            ai_explanation = await self._get_ai_explanation(reason, reason_info.get("name", f"MQRC_{reason}"), original_queue)
            
            # Get current MAXDEPTH for the original queue (if it exists and reason is queue full)
            current_maxdepth = None
            if reason in [2004, 2053] and original_queue and original_queue != "Unknown":
                try:
                    queue_info = self.mcp_server.mq_client.get_queue_info(queue_name=original_queue)
                    current_maxdepth = queue_info.get('max_depth')
                except Exception as e:
                    logger.debug(f"Could not get MAXDEPTH for {original_queue}: {e}")
            
            result = {
                "timestamp": datetime.utcnow().isoformat(),
                "severity": reason_info.get("severity", severity),
                "reason_code": reason,
                "reason_code_name": reason_info.get("name", f"MQRC_{reason}"),
                "reason_description": reason_info["description"],
                "feedback_code": feedback,
                "original_queue": original_queue,
                "message_preview": message_content[:200] if message_content else "No content",
                "recommendations": reason_info["recommendations"],
                "ai_explanation": ai_explanation,
                "actions": self._get_actions_for_message(original_queue, reason)
            }
            
            # Add current_maxdepth if available
            if current_maxdepth is not None:
                result["current_maxdepth"] = current_maxdepth
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing message: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "error",
                "error": str(e),
                "recommendations": ["Manual investigation required"]
            }
    
    async def _get_iam_token(self) -> Optional[str]:
        """Get IAM access token from IBM Cloud using API key."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://iam.cloud.ibm.com/identity/token",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json"
                    },
                    data={
                        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                        "apikey": self.watsonx_api_key
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("access_token")
                else:
                    logger.error(f"IAM token error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Error getting IAM token: {e}")
            return None
    
    async def _get_ai_explanation(self, reason_code: int, reason_name: str, queue_name: str) -> str:
        """Get AI-generated explanation for an MQ reason code using WatsonX."""
        if not self.watsonx_api_key:
            return "AI explanation unavailable (WatsonX API key not configured)"
        
        if not self.watsonx_project_id and not self.watsonx_space_id:
            return "AI explanation unavailable (WatsonX project_id or space_id not configured)"
        
        try:
            # Get IAM token
            iam_token = await self._get_iam_token()
            if not iam_token:
                return "AI explanation unavailable (authentication failed)"
            
            prompt = f"""Explain IBM MQ reason code {reason_code} ({reason_name}) in simple terms.
The message was trying to be delivered to queue: {queue_name}

Provide:
1. What this error means
2. Common causes
3. How to fix it
4. Prevention tips

Keep the explanation concise and practical (max 300 words)."""

            # Use single model - can be configured via env var
            default_model = os.getenv("WATSONX_MODEL_ID", "ibm/granite-13b-chat-v2")
            model_ids = [default_model]
            
            logger.info(f"Using watsonx.ai model: {default_model}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                last_error = "No models available"
                for idx, model_id in enumerate(model_ids):
                    try:
                        # Add delay between requests to avoid rate limiting (2 req/sec limit)
                        if idx > 0:
                            await asyncio.sleep(0.6)  # Wait 600ms between attempts
                        
                        # Build request body - use space_id if available, otherwise project_id
                        request_body = {
                            "input": prompt,
                            "model_id": model_id,
                            "parameters": {
                                "max_new_tokens": 500,
                                "temperature": 0.3,
                                "top_p": 0.9
                            }
                        }
                        
                        # Add either space_id or project_id
                        if self.watsonx_space_id:
                            request_body["space_id"] = self.watsonx_space_id
                        else:
                            request_body["project_id"] = self.watsonx_project_id
                        
                        response = await client.post(
                            f"{self.watsonx_url}/ml/v1/text/generation?version=2023-05-29",
                            headers={
                                "Authorization": f"Bearer {iam_token}",
                                "Content-Type": "application/json",
                                "Accept": "application/json"
                            },
                            json=request_body
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            explanation = result.get("results", [{}])[0].get("generated_text", "").strip()
                            if explanation:
                                logger.info(f"Successfully used model: {model_id}")
                                return explanation
                        elif response.status_code == 429:
                            # Rate limit hit, wait longer and try again
                            last_error = f"Rate limit hit on model {model_id}"
                            logger.warning(last_error)
                            await asyncio.sleep(1.0)  # Wait 1 second on rate limit
                        else:
                            last_error = f"{response.status_code}: {response.text[:200]}"
                            logger.warning(f"Model {model_id} error: {last_error}")
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"Error with model {model_id}: {e}")
                        continue
                
                # If all models failed
                logger.error(f"All models failed. Last error: {last_error}")
                return f"AI explanation unavailable (all models failed: {last_error[:100]})"
                    
        except Exception as e:
            logger.error(f"Error getting AI explanation: {e}")
            return f"AI explanation unavailable (error: {str(e)})"
    
    async def check_deadq(self):
        """Check the dead letter queue for new messages (non-destructive browse)."""
        try:
            # First check if there are any messages in the queue
            queue_info = self.mcp_server.mq_client.get_queue_info(
                queue_name=self.deadq_name
            )
            
            current_depth = queue_info.get("current_depth", 0)
            
            # If queue is empty, clear the alerted messages set
            if current_depth == 0 and self.alerted_messages:
                logger.info(f"DEADQ is empty, clearing {len(self.alerted_messages)} alerted message IDs")
                self.alerted_messages.clear()
                # Also clear the alert buffer in the websocket handler
                if self.websocket_handler:
                    self.websocket_handler.alert_buffer.clear()
                    logger.info("Alert buffer cleared")
            
            if current_depth > 0:
                logger.info(f"{current_depth} message(s) in {self.deadq_name}")
                
                # Browse all messages in the queue (non-destructive)
                # We'll use pymqi directly since MCP browse has issues
                try:
                    qmgr = self.mcp_server.mq_client.qmgr
                    queue = pymqi.Queue(qmgr, self.deadq_name, pymqi.CMQC.MQOO_BROWSE)
                    
                    md = pymqi.MD()
                    gmo = pymqi.GMO()
                    gmo.Options = pymqi.CMQC.MQGMO_BROWSE_FIRST | pymqi.CMQC.MQGMO_NO_WAIT
                    
                    new_alerts = []
                    
                    while True:
                        try:
                            # Create fresh MD for each browse to avoid state issues
                            md = pymqi.MD()
                            message = queue.get(None, md, gmo)
                            message_id = md.MsgId.hex()
                            
                            logger.debug(f"Browsing message: {message_id}, already alerted: {message_id in self.alerted_messages}")
                            
                            # Check if we've already alerted on this message
                            if message_id not in self.alerted_messages:
                                logger.warning(f"New message found in {self.deadq_name}: {message_id}")
                                
                                # Parse DLH if present
                                reason_code = 0
                                feedback_code = 0
                                original_queue = "Unknown"
                                
                                # Check if message starts with DLH header
                                if len(message) >= 108 and message[:4] == b'DLH ':
                                    # DLH structure (first 108 bytes):
                                    # StrucId (4) + Version (4) + Reason (4) + DestQName (48) + DestQMgrName (48)
                                    import struct
                                    # Reason code is at offset 8, 4 bytes, little-endian (Intel)
                                    reason_code = struct.unpack('<I', message[8:12])[0]
                                    # Original queue name at offset 12, 48 bytes (MQ names are space-padded)
                                    original_queue_bytes = message[12:60]
                                    original_queue = original_queue_bytes.decode('utf-8', errors='ignore').rstrip('\x00 ').strip()
                                    # Feedback code is at offset 60, 4 bytes (part of encoding field)
                                    # Queue manager name at offset 60, 48 bytes
                                    qmgr_bytes = message[60:108]
                                    qmgr_name = qmgr_bytes.decode('utf-8', errors='ignore').rstrip('\x00 ').strip()
                                    logger.info(f"Parsed DLH: reason={reason_code}, queue='{original_queue}', qmgr='{qmgr_name}' (queue bytes: {original_queue_bytes[:20].hex()})")
                                    # Note: Feedback code would be after the queue manager name, but we don't need it for auto-resolve
                                    feedback_code = 0  # Not used in current logic
                                
                                # Create message data structure
                                message_data = {
                                    "status": "success",
                                    "queue": self.deadq_name,
                                    "message": message.decode('utf-8', errors='replace'),
                                    "message_id": message_id,
                                    "correlation_id": md.CorrelId.hex(),
                                    "reason": reason_code,
                                    "feedback": feedback_code,
                                    "original_queue": original_queue
                                }
                                
                                # Skip WatsonX analysis for well-known auto-resolvable reason codes
                                # to avoid rate limiting and speed up replay
                                if reason_code in self.auto_resolve_rules and self.auto_resolve_rules.get(reason_code):
                                    analysis = {
                                        "message_id": message_id,
                                        "reason_code": reason_code,
                                        "original_queue": original_queue,
                                        "recommendation": "Auto-resolve rule matched — skipping AI analysis."
                                    }
                                else:
                                    analysis = await self.analyze_dead_message(message_data)
                                    analysis['message_id'] = message_id

                                # Auto-resolve if enabled and rule exists for this reason code
                                is_auto_resolvable = reason_code in self.auto_resolve_rules and self.auto_resolve_rules[reason_code]
                                if self.auto_resolve_enabled and is_auto_resolvable:
                                    logger.info(f"Auto-resolve enabled for reason code {reason_code}, attempting to resolve message {message_id}")
                                    auto_resolve_result = await self.auto_resolve_message(message_id, reason_code, original_queue, analysis)
                                    
                                    if auto_resolve_result.get("status") == "success":
                                        logger.info(f"Auto-resolved message {message_id}: {auto_resolve_result.get('message')}")
                                        self.auto_resolved_messages.add(message_id)
                                        # Add auto-resolve info to analysis
                                        analysis['auto_resolved'] = True
                                        analysis['auto_resolve_action'] = auto_resolve_result.get('action')
                                        analysis['auto_resolve_message'] = auto_resolve_result.get('message')
                                        # Mark as alerted after successful resolution
                                        self.alerted_messages.add(message_id)
                                        # Yield briefly between resolutions to avoid flooding MQ
                                        await asyncio.sleep(0.05)
                                    else:
                                        logger.warning(f"Auto-resolve failed for message {message_id}: {auto_resolve_result.get('message')}")
                                        analysis['auto_resolved'] = False
                                        analysis['auto_resolve_error'] = auto_resolve_result.get('message')
                                        # Do NOT add to alerted_messages — will retry next poll cycle
                                elif is_auto_resolvable:
                                    # Auto-resolve is OFF but this message could be resolved — do NOT
                                    # add to alerted_messages so it gets picked up the moment auto-resolve
                                    # is toggled on, without requiring a pod restart.
                                    pass
                                else:
                                    # No auto-resolve rule — mark alerted to avoid repeated noise
                                    self.alerted_messages.add(message_id)
                                new_alerts.append(analysis)
                            
                            # Move to next message
                            gmo.Options = pymqi.CMQC.MQGMO_BROWSE_NEXT | pymqi.CMQC.MQGMO_NO_WAIT
                            
                        except pymqi.MQMIError as e:
                            if e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                                break  # No more messages
                            else:
                                raise
                    
                    queue.close()
                    
                    # Send all new alerts to UI
                    if new_alerts and self.websocket_handler:
                        for analysis in new_alerts:
                            await self.websocket_handler.broadcast({
                                "type": "deadq_alert",
                                "data": analysis
                            })
                            logger.info(f"Alert sent for message {analysis['message_id']}")
                    
                    return new_alerts if new_alerts else None
                    
                except Exception as browse_error:
                    logger.error(f"Error browsing queue: {browse_error}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking DEADQ: {e}")
            return None
    
    async def start_monitoring(self):
        """Start monitoring the dead letter queue."""
        if not self.connected:
            await self.initialize()
        
        self.monitoring = True
        logger.info(f"Starting DEADQ monitoring (polling every {self.poll_interval}s)")
        
        while self.monitoring:
            try:
                await self.check_deadq()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                if "2009" in str(e) or "CONNECTION_BROKEN" in str(e) or not self.connected:
                    logger.info("MQ connection lost — reconnecting...")
                    self.connected = False
                    await asyncio.sleep(5)
                    try:
                        await self.initialize()
                    except Exception as reinit_err:
                        logger.error(f"Reconnect failed: {reinit_err}")
                else:
                    await asyncio.sleep(self.poll_interval)
    
    async def stop_monitoring(self):
        """Stop monitoring."""
        self.monitoring = False
    
    def _list_queues(self) -> List[str]:
        """
        Return depth-monitorable queue names using only the existing main connection.
        Opens each candidate queue with MQOO_INQUIRE — no second MQ connection needed.
        Uses a comprehensive candidate list compiled from the known queue manager config.
        Results are cached for 5 minutes to avoid opening queue handles every 10s.
        """
        import time
        now = time.monotonic()
        cache = getattr(self, '_queue_list_cache', [])
        cache_ts = getattr(self, '_queue_list_cache_ts', 0.0)
        if cache and (now - cache_ts) < 300.0:
            return cache

        # Full candidate list — covers all app, dev, test, and DLQ queues.
        # Update this list when new queues are created on the queue manager.
        candidates = list(dict.fromkeys([
            self.deadq_name,
            "MIDI.INPUT", "MIDI.OUTPUT",
            "MIDI.INPUT_V2", "MIDI.OUTPUT_V2",
            "MIDI_READ_QUEUE",
            "DEV.QUEUE.1", "DEV.QUEUE.2", "DEV.QUEUE.3",
            "GREG.TEST2",
            "TEST.DLQ.SOURCE", "TEST.FULL.QUEUE",
            "TEST.GREG2", "TEST.GREG3", "TEST.GREG4",
            "TEST.GREGHANSON", "TEST.GREGHANSONW",
        ]))

        qmgr = self.mcp_server.mq_client.qmgr
        accessible = []
        for queue_name in candidates:
            try:
                q = pymqi.Queue(qmgr, queue_name,
                                pymqi.CMQC.MQOO_INQUIRE | pymqi.CMQC.MQOO_FAIL_IF_QUIESCING)
                q.close()
                accessible.append(queue_name)
            except pymqi.MQMIError:
                pass  # queue doesn't exist or not accessible — skip

        self._queue_list_cache = accessible
        self._queue_list_cache_ts = now
        logger.info(f"Queue list: {len(accessible)} accessible queues")
        return accessible

    def _direct_queue_info(self, queue_name: str) -> Optional[Dict]:
        """
        Get queue depth and max depth directly via pymqi MQOO_INQUIRE.
        Avoids PCF (which requires admin OS auth in CP4I) by using direct MQINQ.
        Returns dict with current_depth and max_depth, or None on failure.
        """
        try:
            qmgr = self.mcp_server.mq_client.qmgr
            q = pymqi.Queue(qmgr, queue_name,
                            pymqi.CMQC.MQOO_INQUIRE | pymqi.CMQC.MQOO_FAIL_IF_QUIESCING)
            # pymqi.Queue.inquire() takes individual attribute selectors as positional args
            current_depth = q.inquire(pymqi.CMQC.MQIA_CURRENT_Q_DEPTH)
            max_depth = q.inquire(pymqi.CMQC.MQIA_MAX_Q_DEPTH)
            q.close()
            return {
                'current_depth': int(current_depth),
                'max_depth': int(max_depth),
            }
        except Exception as e:
            logger.debug(f"_direct_queue_info failed for {queue_name}: {e}")
            return None

    async def check_queue_capacity(self) -> Optional[List[Dict[str, Any]]]:
        """
        Check all queues for capacity issues.
        
        Returns:
            List of queues at or above the capacity threshold
        """
        try:
            if not self.connected:
                return None

            queues = self._list_queues()
            capacity_alerts = []

            for queue_name in queues:
                # Skip system queues and the dead letter queue
                if queue_name.startswith('SYSTEM.') or queue_name == self.deadq_name:
                    continue

                try:
                    info = self._direct_queue_info(queue_name)
                    if info is None:
                        continue
                    current_depth = info['current_depth']
                    max_depth = info['max_depth']

                    if max_depth == 0:
                        continue

                    percent_full = (current_depth / max_depth) * 100 if max_depth > 0 else 0

                    if percent_full >= self.capacity_threshold:
                        queue_data = {
                            'queue_name': queue_name,
                            'current_depth': current_depth,
                            'max_depth': max_depth,
                            'percent_full': round(percent_full, 1),
                            'timestamp': datetime.utcnow().isoformat(),
                            'status': self._get_capacity_status(percent_full)
                        }
                        capacity_alerts.append(queue_data)

                        prev_state = self.tracked_queues.get(queue_name, {})
                        if prev_state.get('percent_full', 0) != percent_full:
                            logger.info(f"Queue {queue_name}: {percent_full:.1f}% full ({current_depth}/{max_depth})")
                            self.tracked_queues[queue_name] = queue_data

                except Exception as e:
                    logger.debug(f"Error checking queue {queue_name}: {e}")
                    continue

            for queue_name in list(self.tracked_queues.keys()):
                if not any(q['queue_name'] == queue_name for q in capacity_alerts):
                    logger.info(f"Queue {queue_name} no longer above threshold")
                    del self.tracked_queues[queue_name]

            return capacity_alerts if capacity_alerts else None

        except Exception as e:
            logger.error(f"Error checking queue capacity: {e}")
            return None
    
    def _get_capacity_status(self, percent_full: float) -> str:
        """Get status level based on percentage full."""
        if percent_full >= 90:
            return 'critical'
        elif percent_full >= 80:
            return 'warning'
        elif percent_full >= 70:
            return 'caution'
        else:
            return 'normal'
    
    async def check_all_queues(self) -> List[Dict[str, Any]]:
        """
        Return depth info for every non-system queue plus the DLQ.
        Used by the live queue-depth visualisation page.
        Uses direct MQOO_INQUIRE to avoid PCF which requires admin OS auth in CP4I.
        """
        try:
            if not self.connected:
                return []

            all_queues = self._list_queues()

            # Include all non-system queues + always include the DLQ
            target_queues = [q for q in all_queues if not q.startswith('SYSTEM.')]
            if self.deadq_name not in target_queues:
                target_queues.append(self.deadq_name)

            result = []
            for queue_name in target_queues:
                info = self._direct_queue_info(queue_name)
                if info is None:
                    continue
                current_depth = info['current_depth']
                max_depth = info['max_depth']
                if max_depth == 0:
                    max_depth = 5000  # Fallback so we can still render a bar
                percent_full = round((current_depth / max_depth) * 100, 1) if max_depth > 0 else 0
                result.append({
                    'queue_name': queue_name,
                    'current_depth': current_depth,
                    'max_depth': max_depth,
                    'percent_full': percent_full,
                    'is_dlq': queue_name == self.deadq_name,
                    'status': self._get_capacity_status(percent_full),
                    'timestamp': datetime.utcnow().isoformat(),
                })

            return result
        except Exception as e:
            logger.error(f"Error in check_all_queues: {e}")
            return []

    async def start_capacity_monitoring(self):
        """Start monitoring queue capacity."""
        if not self.connected:
            await self.initialize()
        
        self.capacity_monitoring = True
        logger.info(f"Starting queue capacity monitoring (threshold: {self.capacity_threshold}%, polling every {self.capacity_poll_interval}s)")

        while self.capacity_monitoring:
            try:
                capacity_alerts = await self.check_queue_capacity()
                all_queues = await self.check_all_queues()
                
                # Send capacity updates to UI
                if self.websocket_handler:
                    await self.websocket_handler.broadcast({
                        "type": "capacity_update",
                        "data": {
                            "queues": capacity_alerts or [],
                            "threshold": self.capacity_threshold,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    })
                    # Broadcast full queue-depth snapshot for the live monitor page
                    await self.websocket_handler.broadcast({
                        "type": "queue_depth_update",
                        "data": {
                            "queues": all_queues,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    })
                
                await asyncio.sleep(self.capacity_poll_interval)
            except Exception as e:
                logger.error(f"Error in capacity monitoring loop: {e}")
                if "2009" in str(e) or "CONNECTION_BROKEN" in str(e) or not self.connected:
                    logger.info("MQ connection lost in capacity monitor — reconnecting...")
                    self.connected = False
                    await asyncio.sleep(5)
                    try:
                        await self.initialize()
                    except Exception as reinit_err:
                        logger.error(f"Reconnect failed: {reinit_err}")
                await asyncio.sleep(self.capacity_poll_interval)
    
    async def stop_capacity_monitoring(self):
        """Stop capacity monitoring."""
        self.capacity_monitoring = False
        logger.info("Stopping queue capacity monitoring")
    
    def set_capacity_threshold(self, threshold: int):
        """Set the capacity threshold percentage."""
        if 0 <= threshold <= 100:
            self.capacity_threshold = threshold
            logger.info(f"Capacity threshold set to {threshold}%")
            return True
        return False
        logger.info("Stopping DEADQ monitoring")
    
    async def execute_action(self, action_id: str, message_id: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an approved action on a dead letter message.
        
        Args:
            action_id: Action to execute
            message_id: Message identifier (hex string or numeric timestamp)
            **kwargs: Additional parameters (e.g., new_maxdepth for increase_maxdepth action)
            
        Returns:
            Result of the action
        """
        try:
            qmgr = self.mcp_server.mq_client.qmgr
            
            # If message_id is numeric (timestamp), we need to browse and find the message
            # The frontend might be sending a timestamp instead of the hex message_id
            if message_id.isdigit():
                logger.warning(f"Received numeric message_id: {message_id}, this appears to be a timestamp. Browsing queue to find matching message.")
                return {
                    "status": "error",
                    "message": "Frontend is sending incorrect message_id. Please refresh the page and try again. The message_id should be a 48-character hex string, not a timestamp."
                }
            
            if action_id == "delete_message":
                # Find and delete the specific message by message ID
                queue = pymqi.Queue(qmgr, self.deadq_name, pymqi.CMQC.MQOO_INPUT_AS_Q_DEF)
                
                md = pymqi.MD()
                gmo = pymqi.GMO()
                gmo.Options = pymqi.CMQC.MQGMO_NO_WAIT
                gmo.MatchOptions = pymqi.CMQC.MQMO_MATCH_MSG_ID
                # Clean the message_id: remove all non-hex characters
                import re
                clean_message_id = re.sub(r'[^0-9a-fA-F]', '', message_id)
                logger.info(f"Delete message request - Original ID: {message_id}, Cleaned ID: {clean_message_id}")
                
                if len(clean_message_id) != 48:  # MQ message IDs are 24 bytes = 48 hex chars
                    queue.close()
                    return {
                        "status": "error",
                        "message": f"Invalid message ID length: expected 48 hex chars, got {len(clean_message_id)}"
                    }
                
                try:
                    md.MsgId = bytes.fromhex(clean_message_id)
                except ValueError as e:
                    queue.close()
                    return {
                        "status": "error",
                        "message": f"Invalid message ID format after cleaning: {str(e)}"
                    }
                
                try:
                    message = queue.get(None, md, gmo)
                    queue.close()
                    
                    # Remove from alerted set (use clean_message_id which is the actual hex string)
                    self.alerted_messages.discard(clean_message_id)
                    
                    # Remove from alert buffer and notify clients
                    if self.websocket_handler:
                        self.websocket_handler.alert_buffer = [
                            alert for alert in self.websocket_handler.alert_buffer
                            if alert.get('data', {}).get('message_id') != clean_message_id
                        ]
                        logger.info(f"Removed message {clean_message_id} from alert buffer")
                        
                        # Broadcast removal to all connected clients
                        await self.websocket_handler.broadcast({
                            "type": "alert_removed",
                            "data": {
                                "message_id": clean_message_id
                            }
                        })
                        logger.info(f"Broadcasted alert removal for message {clean_message_id}")
                    
                    logger.info(f"Message {clean_message_id} deleted from DEADQ")
                    return {
                        "status": "success",
                        "message": "Message deleted from DEADQ"
                    }
                except pymqi.MQMIError as e:
                    queue.close()
                    if e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                        return {
                            "status": "error",
                            "message": "Message not found (may have been already processed)"
                        }
                    raise
            
            elif action_id == "replay_message":
                # Find the message, get it, and replay to original queue
                # Clean the message_id first
                import re
                clean_msg_id = re.sub(r'[^0-9a-fA-F]', '', message_id)
                logger.info(f"Starting replay_message for message_id: {clean_msg_id}")
                
                browse_queue = None
                put_queue = None
                
                try:
                    # Browse to find the message and extract queue name from DLH
                    browse_queue = pymqi.Queue(qmgr, self.deadq_name, pymqi.CMQC.MQOO_BROWSE)
                    
                    md = pymqi.MD()
                    gmo = pymqi.GMO()
                    gmo.Options = pymqi.CMQC.MQGMO_BROWSE_FIRST | pymqi.CMQC.MQGMO_NO_WAIT
                    
                    message_found = None
                    original_queue = None
                    
                    while True:
                        try:
                            md = pymqi.MD()
                            message = browse_queue.get(None, md, gmo)
                            msg_id_hex = md.MsgId.hex()
                            
                            if msg_id_hex == clean_msg_id:
                                message_found = message
                                logger.info(f"Found matching message, length: {len(message)}")
                                
                                # Extract queue name from DLH
                                # DLH structure: StrucId(4) + Version(4) + Reason(4) + DestQName(48) + DestQMgrName(48)...
                                # DestQName starts at offset 12 (after StrucId, Version, Reason)
                                if len(message) >= 60:
                                    queue_name_bytes = message[12:60]
                                    original_queue = queue_name_bytes.decode('utf-8', errors='ignore').rstrip('\x00').strip()
                                    logger.info(f"Extracted queue name from DLH: '{original_queue}'")
                                else:
                                    logger.warning(f"Message too short ({len(message)} bytes) to contain DLH")
                                break
                            gmo.Options = pymqi.CMQC.MQGMO_BROWSE_NEXT | pymqi.CMQC.MQGMO_NO_WAIT
                        except pymqi.MQMIError as e:
                            if e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                                break
                            raise
                    
                    # Close browse queue immediately
                    if browse_queue:
                        browse_queue.close()
                        browse_queue = None
                        logger.info("Browse queue closed")
                    
                    if not message_found:
                        logger.error("Message not found in DEADQ")
                        return {
                            "status": "error",
                            "message": "Message not found in DEADQ"
                        }
                    
                    if not original_queue:
                        logger.error("Could not extract queue name from message")
                        return {
                            "status": "error",
                            "message": "Could not extract original queue name from message. The message may not have a proper Dead Letter Header."
                        }
                    
                    # Check if queue is full and increase MAXDEPTH if needed
                    try:
                        queue_info = self.mcp_server.mq_client.get_queue_info(queue_name=original_queue)
                        current_depth = queue_info.get('current_depth', 0)
                        max_depth = queue_info.get('max_depth', 5000)
                        
                        # If queue is at or near capacity, increase MAXDEPTH
                        if current_depth >= max_depth:
                            new_maxdepth = int(max_depth * 1.5)
                            logger.info(f"Queue {original_queue} is full ({current_depth}/{max_depth}), increasing MAXDEPTH to {new_maxdepth}")
                            
                            # Use MQSC command to change queue attributes
                            try:
                                mqsc_command = f"ALTER QLOCAL({original_queue.strip()}) MAXDEPTH({new_maxdepth})"
                                result = self.mcp_server.mq_client.execute_mqsc(mqsc_command=mqsc_command)
                                logger.info(f"Successfully increased MAXDEPTH on {original_queue} from {max_depth} to {new_maxdepth}: {result}")
                                
                                # Verify the change took effect
                                import time
                                time.sleep(0.5)  # Brief pause for change to propagate
                                updated_info = self.mcp_server.mq_client.get_queue_info(queue_name=original_queue)
                                logger.info(f"Verified MAXDEPTH is now {updated_info.get('max_depth')}")
                            except Exception as mqsc_error:
                                logger.error(f"MQSC error changing queue: {mqsc_error}")
                                # Continue anyway - try to put the message
                    except Exception as e:
                        logger.warning(f"Could not check/increase queue depth: {e}")
                        # Continue anyway - try to put the message
                    
                    # Put to original queue
                    put_queue = pymqi.Queue(qmgr, original_queue, pymqi.CMQC.MQOO_OUTPUT)
                    put_md = pymqi.MD()
                    put_queue.put(message_found, put_md)
                    
                    # Close put queue immediately
                    if put_queue:
                        put_queue.close()
                        put_queue = None
                        logger.info(f"Put queue '{original_queue}' closed after message replay")
                    
                    # Now delete from DEADQ
                    delete_result = await self.execute_action("delete_message", message_id)
                    
                    logger.info(f"Message replayed to {original_queue} and removed from DEADQ")
                    return {
                        "status": "success",
                        "message": f"Message replayed to {original_queue} and removed from DEADQ"
                    }
                    
                except Exception as e:
                    logger.error(f"Error in replay_message: {str(e)}")
                    return {
                        "status": "error",
                        "message": f"Failed to replay message: {str(e)}"
                    }
                finally:
                    # Ensure all queue handles are closed
                    if browse_queue:
                        try:
                            browse_queue.close()
                            logger.info("Browse queue closed in finally block")
                        except:
                            pass
                    if put_queue:
                        try:
                            put_queue.close()
                            logger.info("Put queue closed in finally block")
                        except:
                            pass
            
            elif action_id == "create_and_replay":
                # Create queue and replay message
                # Clean the message_id first
                import re
                clean_msg_id = re.sub(r'[^0-9a-fA-F]', '', message_id)
                logger.info(f"Starting create_and_replay for message_id: {clean_msg_id}")
                
                browse_queue = None
                put_queue = None
                
                try:
                    # First, we need to get the original queue name from the message
                    # Browse to find the message and extract the queue name from DLH
                    browse_queue = pymqi.Queue(qmgr, self.deadq_name, pymqi.CMQC.MQOO_BROWSE)
                    
                    md = pymqi.MD()
                    gmo = pymqi.GMO()
                    gmo.Options = pymqi.CMQC.MQGMO_BROWSE_FIRST | pymqi.CMQC.MQGMO_NO_WAIT
                    
                    message_found = None
                    queue_name_to_create = None
                    
                    while True:
                        try:
                            md = pymqi.MD()
                            message = browse_queue.get(None, md, gmo)
                            msg_id_hex = md.MsgId.hex()
                            logger.info(f"Browsing message with ID: {msg_id_hex}, looking for: {clean_msg_id}")
                            
                            if msg_id_hex == clean_msg_id:
                                message_found = message
                                logger.info(f"Found matching message, length: {len(message)}")
                                logger.info(f"First 100 bytes (hex): {message[:100].hex()}")
                                
                                # Try to extract queue name from DLH
                                # DLH structure: StrucId(4) + Version(4) + Reason(4) + DestQName(48) + DestQMgrName(48)...
                                # DestQName starts at offset 12 (after StrucId, Version, Reason)
                                if len(message) >= 60:
                                    queue_name_bytes = message[12:60]
                                    logger.info(f"Queue name bytes (hex): {queue_name_bytes.hex()}")
                                    # Decode and clean the queue name - remove null bytes and whitespace
                                    queue_name_to_create = queue_name_bytes.decode('utf-8', errors='ignore').rstrip('\x00').strip()
                                    logger.info(f"Extracted queue name from DLH: '{queue_name_to_create}'")
                                else:
                                    logger.warning(f"Message too short ({len(message)} bytes) to contain DLH")
                                break
                            gmo.Options = pymqi.CMQC.MQGMO_BROWSE_NEXT | pymqi.CMQC.MQGMO_NO_WAIT
                        except pymqi.MQMIError as e:
                            if e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                                logger.info("No more messages to browse")
                                break
                            raise
                    
                    # Close browse queue immediately after finding the message
                    if browse_queue:
                        browse_queue.close()
                        browse_queue = None
                        logger.info("Browse queue closed")
                    
                    if not message_found:
                        logger.error("Message not found in DEADQ")
                        return {
                            "status": "error",
                            "message": "Message not found in DEADQ"
                        }
                    
                    if not queue_name_to_create:
                        logger.error("Could not extract queue name from message")
                        return {
                            "status": "error",
                            "message": "Could not extract queue name from message"
                        }
                    
                    # Create the queue using MCP server
                    try:
                        result = self.mcp_server.mq_client.create_queue(
                            queue_name=queue_name_to_create,
                            max_depth=5000,
                            max_msg_length=4194304
                        )
                        logger.info(f"Created queue: {queue_name_to_create}")
                    except Exception as e:
                        logger.warning(f"Queue creation failed (may already exist): {e}")
                    
                    # Now replay the message to the newly created queue
                    put_queue = pymqi.Queue(qmgr, queue_name_to_create, pymqi.CMQC.MQOO_OUTPUT)
                    put_md = pymqi.MD()
                    put_queue.put(message_found, put_md)
                    
                    # Close the put queue immediately after putting the message
                    if put_queue:
                        put_queue.close()
                        put_queue = None
                        logger.info(f"Put queue '{queue_name_to_create}' closed immediately after message replay")
                    
                    # Delete from DEADQ
                    delete_result = await self.execute_action("delete_message", message_id)
                    
                    return {
                        "status": "success",
                        "message": f"Queue '{queue_name_to_create}' created and message replayed successfully. Queue handle closed."
                    }
                    
                except Exception as e:
                    logger.error(f"Error in create_and_replay: {str(e)}")
                    return {
                        "status": "error",
                        "message": f"Failed to replay message: {str(e)}"
                    }
                finally:
                    # Ensure all queue handles are closed even if an error occurs
                    if browse_queue:
                        try:
                            browse_queue.close()
                            logger.info("Browse queue closed in finally block")
                        except:
                            pass
                    if put_queue:
                        try:
                            put_queue.close()
                            logger.info("Put queue closed in finally block")
                        except:
                            pass
            
            elif action_id == "investigate":
                # Get queue info for investigation
                queue_info = self.mcp_server.mq_client.get_queue_info(
                    queue_name=self.deadq_name
                )
                
                return {
                    "status": "success",
                    "message": "Investigation started - check logs and queue manager",
                    "queue_info": queue_info
                }
            
            elif action_id == "increase_maxdepth":
                # Increase MAXDEPTH on the queue
                # Check if queue_name is passed directly (for capacity monitoring)
                queue_name = kwargs.get('queue_name')
                from_capacity_monitor = bool(queue_name)  # Track if called from capacity monitor
                
                browse_queue = None
                try:
                    # If queue_name not provided, extract from DEADQ message
                    if not queue_name:
                        import re
                        clean_msg_id = re.sub(r'[^0-9a-fA-F]', '', message_id)
                        
                        # Browse to find the message and extract queue name
                        browse_queue = pymqi.Queue(qmgr, self.deadq_name, pymqi.CMQC.MQOO_BROWSE)
                        
                        md = pymqi.MD()
                        gmo = pymqi.GMO()
                        gmo.Options = pymqi.CMQC.MQGMO_BROWSE_FIRST | pymqi.CMQC.MQGMO_NO_WAIT
                        
                        while True:
                            try:
                                md = pymqi.MD()
                                message = browse_queue.get(None, md, gmo)
                                msg_id_hex = md.MsgId.hex()
                                
                                if msg_id_hex == clean_msg_id:
                                    # Extract queue name from DLH
                                    if len(message) >= 60:
                                        queue_name_bytes = message[12:60]
                                        queue_name = queue_name_bytes.decode('utf-8', errors='ignore').rstrip('\x00').strip()
                                    break
                                gmo.Options = pymqi.CMQC.MQGMO_BROWSE_NEXT | pymqi.CMQC.MQGMO_NO_WAIT
                            except pymqi.MQMIError as e:
                                if e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                                    break
                                raise
                        
                        if browse_queue:
                            browse_queue.close()
                            browse_queue = None
                        
                        if not queue_name:
                            return {
                                "status": "error",
                                "message": "Could not extract queue name from message"
                            }
                    
                    # Get current MAXDEPTH
                    queue_info = self.mcp_server.mq_client.get_queue_info(queue_name=queue_name)
                    current_maxdepth = queue_info.get('max_depth', 5000)
                    
                    # Get new_maxdepth from kwargs, or default to 50% increase
                    new_maxdepth = kwargs.get('new_maxdepth')
                    if new_maxdepth:
                        new_maxdepth = int(new_maxdepth)
                    else:
                        new_maxdepth = int(current_maxdepth * 1.5)
                    
                    # Validate new_maxdepth
                    if new_maxdepth <= current_maxdepth:
                        raise Exception(f"New MAXDEPTH ({new_maxdepth}) must be greater than current MAXDEPTH ({current_maxdepth})")
                    
                    if new_maxdepth > 999999999:
                        raise Exception(f"New MAXDEPTH ({new_maxdepth}) exceeds maximum allowed value (999999999)")
                    
                    # Use MQSC command to change queue attributes
                    try:
                        mqsc_command = f"ALTER QLOCAL({queue_name}) MAXDEPTH({new_maxdepth})"
                        result = self.mcp_server.mq_client.execute_mqsc(mqsc_command=mqsc_command)
                        
                        # Check if the command failed
                        if result.get("status") == "error":
                            error_msg = result.get("message", "Unknown error")
                            logger.error(f"MQSC command failed: {error_msg}")
                            raise Exception(f"Failed to change MAXDEPTH: {error_msg}")
                        
                        logger.info(f"Successfully increased MAXDEPTH on {queue_name} from {current_maxdepth} to {new_maxdepth}: {result}")
                        
                        # Verify the change took effect
                        import time
                        time.sleep(0.5)  # Brief pause for change to propagate
                        updated_info = self.mcp_server.mq_client.get_queue_info(queue_name=queue_name)
                        logger.info(f"Verified MAXDEPTH is now {updated_info.get('max_depth')}")
                    except Exception as mqsc_error:
                        logger.error(f"MQSC error changing queue: {mqsc_error}")
                        raise Exception(f"Failed to change MAXDEPTH: {mqsc_error}")
                    
                    # Only replay message if called from DEADQ monitoring (not capacity monitoring)
                    if from_capacity_monitor:
                        # Capacity monitoring: just return success after increasing MAXDEPTH
                        return {
                            "status": "success",
                            "message": f"Increased MAXDEPTH on {queue_name} from {current_maxdepth} to {new_maxdepth}"
                        }
                    else:
                        # DEADQ monitoring: replay the message after increasing MAXDEPTH
                        logger.info(f"Attempting to replay message {message_id} to {queue_name} after MAXDEPTH increase")
                        replay_result = await self.execute_action("replay_message", message_id)
                        
                        if replay_result.get("status") == "success":
                            return {
                                "status": "success",
                                "message": f"Increased MAXDEPTH on {queue_name} from {current_maxdepth} to {new_maxdepth} and replayed message successfully"
                            }
                        else:
                            return {
                                "status": "partial_success",
                                "message": f"Increased MAXDEPTH on {queue_name} from {current_maxdepth} to {new_maxdepth}, but failed to replay message: {replay_result.get('message', 'Unknown error')}"
                            }
                    
                except Exception as e:
                    logger.error(f"Error increasing MAXDEPTH: {str(e)}")
                    return {
                        "status": "error",
                        "message": f"Failed to increase MAXDEPTH: {str(e)}"
                    }
                finally:
                    if browse_queue:
                        try:
                            browse_queue.close()
                        except:
                            pass
            
            elif action_id == "view_details":
                # Just return success - details are already in the UI
                return {
                    "status": "success",
                    "message": "Message details displayed"
                }
            
            else:
                return {
                    "status": "error",
                    "message": f"Unknown action: {action_id}"
                }
                
        except Exception as e:
            logger.error(f"Error executing action {action_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def execute_bulk_action(self, action: str, message_ids: List[str]) -> Dict[str, Any]:
        """
        Execute a bulk action on multiple messages.
        
        Args:
            action: The action to perform ("delete" or "replay_and_delete")
            message_ids: List of message IDs to process
            
        Returns:
            Dictionary with results for each message
        """
        results = {
            "total": len(message_ids),
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        for message_id in message_ids:
            try:
                if action == "delete":
                    result = await self.execute_action("delete_message", message_id)
                elif action == "replay_and_delete":
                    # replay_message already deletes the message from DEADQ after replaying
                    result = await self.execute_action("replay_message", message_id)
                else:
                    result = {
                        "status": "error",
                        "message": f"Unknown action: {action}"
                    }
                
                if result.get("status") == "success":
                    results["successful"] += 1
                    results["details"].append({
                        "message_id": message_id,
                        "status": "success",
                        "message": result.get("message", "Success")
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "message_id": message_id,
                        "status": "error",
                        "message": result.get("message", "Unknown error")
                    })
                    
            except Exception as e:
                logger.error(f"Error processing message {message_id}: {e}")
                results["failed"] += 1
                results["details"].append({
                    "message_id": message_id,
                    "status": "error",
                    "message": str(e)
                })
        
        return {
            "status": "success" if results["failed"] == 0 else "partial_success",
            "message": f"Processed {results['successful']}/{results['total']} messages successfully",
            "results": results
        }
    
    async def auto_resolve_message(self, message_id: str, reason_code: int, original_queue: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically resolve a DEADQ message based on its reason code.
        Logs all actions to the audit log for review.
        
        Args:
            message_id: The message ID
            reason_code: The MQ reason code
            original_queue: The original queue name
            analysis: The message analysis data
            
        Returns:
            Dictionary with resolution status and details
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message_id": message_id,
            "reason_code": reason_code,
            "original_queue": original_queue,
            "action": None,
            "status": None,
            "details": None
        }
        
        try:
            logger.info(f"Auto-resolving message {message_id} with reason code {reason_code}")
            
            # MQRC_Q_FULL (2053) - Queue is full
            if reason_code == 2053:
                logger.info(f"Auto-resolving MQRC_Q_FULL for queue {original_queue}")
                audit_entry["action"] = "increase_maxdepth_and_replay"
                
                try:
                    # Get current queue info
                    queue_info = self.mcp_server.mq_client.get_queue_info(queue_name=original_queue)
                    current_maxdepth = queue_info.get('max_depth', 5000)
                    current_depth = queue_info.get('current_depth', 0)

                    # Only ALTER once per queue per session — skip if already done
                    if original_queue not in self.queues_already_altered:
                        # New MAXDEPTH = max(current maxdepth, current depth) + 100
                        new_maxdepth = max(current_maxdepth, current_depth) + 100
                        mqsc_command = f"ALTER QLOCAL({original_queue}) MAXDEPTH({new_maxdepth})"
                        result = self.mcp_server.mq_client.execute_mqsc(mqsc_command=mqsc_command)

                        if result.get("status") == "error":
                            error_msg = result.get("message", "Unknown error")
                            raise Exception(f"Failed to change MAXDEPTH: {error_msg}")

                        self.queues_already_altered.add(original_queue)
                        logger.info(f"Increased MAXDEPTH on {original_queue} from {current_maxdepth} to {new_maxdepth} (one-time alter)")
                    else:
                        new_maxdepth = current_maxdepth
                        logger.info(f"Skipping ALTER on {original_queue} — already altered this session, replaying message only")
                    
                    # Replay the message
                    replay_result = await self.execute_action("replay_message", message_id)
                    
                    if replay_result.get("status") == "success":
                        audit_entry["status"] = "success"
                        audit_entry["details"] = f"Increased MAXDEPTH from {current_maxdepth} to {new_maxdepth} and replayed message"
                        self._add_audit_entry(audit_entry)
                        return {
                            "status": "success",
                            "action": "increase_maxdepth_and_replay",
                            "message": audit_entry["details"]
                        }
                    else:
                        audit_entry["status"] = "partial_success"
                        audit_entry["details"] = f"Increased MAXDEPTH from {current_maxdepth} to {new_maxdepth} but failed to replay: {replay_result.get('message')}"
                        self._add_audit_entry(audit_entry)
                        return {
                            "status": "partial_success",
                            "action": "increase_maxdepth",
                            "message": audit_entry["details"]
                        }
                        
                except Exception as e:
                    logger.error(f"Error auto-resolving MQRC_Q_FULL: {e}")
                    audit_entry["status"] = "error"
                    audit_entry["details"] = f"Failed to auto-resolve: {str(e)}"
                    self._add_audit_entry(audit_entry)
                    return {
                        "status": "error",
                        "action": "increase_maxdepth_and_replay",
                        "message": audit_entry["details"]
                    }
            
            # MQRC_UNKNOWN_OBJECT_NAME (2085) - Queue doesn't exist
            elif reason_code == 2085:
                logger.info(f"Auto-resolving MQRC_UNKNOWN_OBJECT_NAME for queue {original_queue}")
                audit_entry["action"] = "create_queue_and_replay"
                
                try:
                    # Create the queue
                    self.mcp_server.mq_client.create_queue(
                        queue_name=original_queue,
                        max_depth=5000,
                        max_msg_length=4194304
                    )
                    logger.info(f"Created queue {original_queue}")
                    
                    # Replay the message
                    replay_result = await self.execute_action("replay_message", message_id)
                    
                    if replay_result.get("status") == "success":
                        audit_entry["status"] = "success"
                        audit_entry["details"] = f"Created queue {original_queue} and replayed message"
                        self._add_audit_entry(audit_entry)
                        return {
                            "status": "success",
                            "action": "create_queue_and_replay",
                            "message": audit_entry["details"]
                        }
                    else:
                        audit_entry["status"] = "partial_success"
                        audit_entry["details"] = f"Created queue {original_queue} but failed to replay: {replay_result.get('message')}"
                        self._add_audit_entry(audit_entry)
                        return {
                            "status": "partial_success",
                            "action": "create_queue",
                            "message": audit_entry["details"]
                        }
                        
                except Exception as e:
                    logger.error(f"Error auto-resolving MQRC_UNKNOWN_OBJECT_NAME: {e}")
                    audit_entry["status"] = "error"
                    audit_entry["details"] = f"Failed to auto-resolve: {str(e)}"
                    self._add_audit_entry(audit_entry)
                    return {
                        "status": "error",
                        "action": "create_queue_and_replay",
                        "message": audit_entry["details"]
                    }
            
            else:
                audit_entry["action"] = "unknown"
                audit_entry["status"] = "error"
                audit_entry["details"] = f"No auto-resolve rule for reason code {reason_code}"
                self._add_audit_entry(audit_entry)
                return {
                    "status": "error",
                    "action": "unknown",
                    "message": audit_entry["details"]
                }
                
        except Exception as e:
            logger.error(f"Error in auto_resolve_message: {e}")
            audit_entry["status"] = "error"
            audit_entry["details"] = f"Auto-resolve failed: {str(e)}"
            self._add_audit_entry(audit_entry)
            return {
                "status": "error",
                "action": "unknown",
                "message": audit_entry["details"]
            }
    
    def _add_audit_entry(self, entry: Dict[str, Any]):
        """Add an entry to the audit log, maintaining max size."""
        self.auto_resolve_audit_log.append(entry)
        # Keep only the last N entries
        if len(self.auto_resolve_audit_log) > self.max_audit_log_entries:
            self.auto_resolve_audit_log = self.auto_resolve_audit_log[-self.max_audit_log_entries:]
    
    def get_auto_resolve_audit_log(self) -> List[Dict[str, Any]]:
        """Get the auto-resolve audit log (most recent first)."""
        return list(reversed(self.auto_resolve_audit_log))
    
    def toggle_auto_resolve(self, enabled: bool) -> Dict[str, Any]:
        """Toggle auto-resolve on/off."""
        self.auto_resolve_enabled = enabled
        if enabled:
            # Reset tracking so all current DLQ messages are re-evaluated through auto-resolve
            self.queues_already_altered.clear()
            cleared = len(self.alerted_messages)
            self.alerted_messages.clear()
            logger.info(f"Auto-resolve enabled — cleared {cleared} alerted message IDs so existing DLQ messages will be re-processed")
        logger.info(f"Auto-resolve {'enabled' if enabled else 'disabled'}")
        return {
            "status": "success",
            "enabled": self.auto_resolve_enabled,
            "message": f"Auto-resolve {'enabled' if enabled else 'disabled'}"
        }
    
    def get_auto_resolve_status(self) -> Dict[str, Any]:
        """Get current auto-resolve status and configuration."""
        return {
            "enabled": self.auto_resolve_enabled,
            "rules": self.auto_resolve_rules,
            "resolved_count": len(self.auto_resolved_messages),
            "audit_log_count": len(self.auto_resolve_audit_log)
        }
    
    async def shutdown(self):
        """Shutdown the monitor."""
        await self.stop_monitoring()
        if self.connected:
            try:
                self.mcp_server.mq_client.disconnect()
                logger.info("Disconnected from MQ")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


# Made with Bob