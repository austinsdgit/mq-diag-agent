"""
MQ Diagnostic Agent - Main API Server
Provides REST API and WebSocket for real-time DEADQ monitoring
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import asyncio
import json
import logging
import os
import bcrypt
import secrets
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from backend.monitor import DeadQueueMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Token storage (in-memory for simplicity)
active_tokens: Dict[str, Dict[str, Any]] = {}

def load_users() -> Dict[str, Any]:
    """Load users from auth_users.json file."""
    users_file = os.getenv("USERS_FILE", "/app/auth_users.json")
    try:
        with open(users_file, 'r') as f:
            data = json.load(f)
            return data.get("users", {})
    except Exception as e:
        logger.error(f"Failed to load users file: {e}")
        return {}

def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify authentication token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Extract token from "Bearer <token>" format
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication format")
    
    token = authorization.replace("Bearer ", "")
    
    if token not in active_tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    token_data = active_tokens[token]
    
    # Check if token is expired (24 hour expiry)
    if datetime.now() > token_data["expires"]:
        del active_tokens[token]
        raise HTTPException(status_code=401, detail="Token expired")
    
    return token_data["username"]


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Login response model."""
    token: str
    username: str
    expires: str

app = FastAPI(title="MQ Diagnostic Agent API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WebSocketManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.alert_buffer: List[dict] = []  # Buffer to store recent alerts
        self.max_buffer_size = 100  # Keep last 100 alerts
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
        # Send buffered alerts to newly connected client
        if self.alert_buffer:
            logger.info(f"Sending {len(self.alert_buffer)} buffered alerts to new client")
            for alert in self.alert_buffer:
                try:
                    await websocket.send_json(alert)
                except Exception as e:
                    logger.error(f"Error sending buffered alert: {e}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients and buffer it."""
        # Add to buffer
        self.alert_buffer.append(message)
        if len(self.alert_buffer) > self.max_buffer_size:
            self.alert_buffer.pop(0)  # Remove oldest alert
        
        # Broadcast to all connected clients
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


# Global instances
ws_manager = WebSocketManager()
monitor = DeadQueueMonitor(websocket_handler=ws_manager)
monitor_task = None
capacity_monitor_task = None


class ActionRequest(BaseModel):
    action_id: str
    message_id: str
    approved: bool = False
    new_maxdepth: Optional[int] = None  # For increase_maxdepth action
    queue_name: Optional[str] = None  # For capacity monitoring increase_maxdepth


class BulkActionRequest(BaseModel):
    action: str  # "delete" or "replay_and_delete"
    message_ids: List[str]
    approved: bool = False


class MonitorStatus(BaseModel):
    monitoring: bool
    connected: bool
    deadq_name: str
    poll_interval: int
    active_connections: int


@app.on_event("startup")
async def startup_event():
    """Start the monitor on application startup."""
    global monitor_task, capacity_monitor_task
    try:
        await monitor.initialize()
        monitor_task = asyncio.create_task(monitor.start_monitoring())
        capacity_monitor_task = asyncio.create_task(monitor.start_capacity_monitoring())
        logger.info("DEADQ and capacity monitoring started")
    except Exception as e:
        logger.error(f"Failed to start monitoring: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the monitor on application shutdown."""
    global monitor_task, capacity_monitor_task
    if monitor_task:
        await monitor.stop_monitoring()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    if capacity_monitor_task:
        await monitor.stop_capacity_monitoring()
        capacity_monitor_task.cancel()
        try:
            await capacity_monitor_task
        except asyncio.CancelledError:
            pass
    await monitor.shutdown()
    logger.info("DEADQ and capacity monitoring stopped")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main frontend HTML - auth check happens in JavaScript."""
    try:
        with open("/app/frontend/index.html", "r") as f:
            content = f.read()
            return HTMLResponse(
                content=content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>MQ Diagnostic Agent</h1><p>Frontend not found.</p>",
            status_code=200
        )

@app.get("/login.html", response_class=HTMLResponse)
async def login_page():
    """Serve the login page."""
    try:
        with open("/app/frontend/login.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Login Required</h1><p>Please configure authentication.</p>",
            status_code=200
        )

@app.get("/queue-monitor", response_class=HTMLResponse)
async def queue_monitor_page():
    """Serve the live queue-depth visualisation page."""
    try:
        with open("/app/frontend/queue-monitor.html", "r") as f:
            content = f.read()
            return HTMLResponse(
                content=content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Queue Monitor</h1><p>Frontend not found.</p>",
            status_code=200
        )

@app.get("/api")
async def api_root(username: str = Depends(verify_token)):
    """API root endpoint."""
    return {
        "service": "MQ Diagnostic Agent",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "status": "/api/status",
            "websocket": "/ws",
            "actions": "/api/action"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint - no authentication required."""
    return {
        "status": "healthy",
        "monitoring": monitor.monitoring,
        "connected": monitor.connected,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login endpoint - no authentication required."""
    users = load_users()
    
    logger.info(f"Login attempt for user: {request.username}")
    
    if request.username not in users:
        logger.warning(f"User not found: {request.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = users[request.username]
    password_hash_str = user.get("password", "")
    
    logger.info(f"Hash from file (first 20 chars): {password_hash_str[:20]}")
    
    # Verify password using bcrypt
    # The hash from JSON is a string, need to encode it to bytes
    try:
        password_bytes = request.password.encode('utf-8')
        hash_bytes = password_hash_str.encode('utf-8')
        
        logger.info(f"Password length: {len(password_bytes)}, Hash length: {len(hash_bytes)}")
        
        if not bcrypt.checkpw(password_bytes, hash_bytes):
            logger.warning(f"Password mismatch for user: {request.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        logger.info(f"Password verified successfully for user: {request.username}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password verification error for {request.username}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate token
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=24)
    
    # Store token
    active_tokens[token] = {
        "username": request.username,
        "expires": expires
    }
    
    logger.info(f"User '{request.username}' logged in successfully")
    
    return LoginResponse(
        token=token,
        username=request.username,
        expires=expires.isoformat()
    )



@app.get("/api/status", response_model=MonitorStatus)
async def get_status(username: str = Depends(verify_token)):
    """Get monitoring status."""
    return MonitorStatus(
        monitoring=monitor.monitoring,
        connected=monitor.connected,
        deadq_name=monitor.deadq_name,
        poll_interval=monitor.poll_interval,
        active_connections=len(ws_manager.active_connections)
    )


@app.post("/api/action")
async def execute_action(request: ActionRequest, username: str = Depends(verify_token)):
    """
    Execute an action on a dead letter message.
    Requires approval for destructive actions.
    """
    if not request.approved and request.action_id in ["replay_message", "delete_message", "create_and_replay", "increase_maxdepth"]:
        raise HTTPException(
            status_code=400,
            detail="This action requires approval"
        )
    
    try:
        # Pass additional parameters to execute_action
        kwargs = {}
        if request.new_maxdepth is not None:
            kwargs['new_maxdepth'] = request.new_maxdepth
        if request.queue_name is not None:
            kwargs['queue_name'] = request.queue_name
        
        result = await monitor.execute_action(request.action_id, request.message_id, **kwargs)
        
        # Broadcast action result to all connected clients
        await ws_manager.broadcast({
            "type": "action_result",
            "data": {
                "action_id": request.action_id,
                "message_id": request.message_id,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        return result
    except Exception as e:
        logger.error(f"Error executing action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk-action")
async def execute_bulk_action(request: BulkActionRequest, username: str = Depends(verify_token)):
    """
    Execute a bulk action on multiple dead letter messages.
    Requires approval for destructive actions.
    """
    if not request.approved:
        raise HTTPException(
            status_code=400,
            detail="This action requires approval"
        )
    
    if not request.message_ids:
        raise HTTPException(
            status_code=400,
            detail="No message IDs provided"
        )
    
    try:
        result = await monitor.execute_bulk_action(request.action, request.message_ids)
        
        # Broadcast bulk action result to all connected clients
        await ws_manager.broadcast({
            "type": "bulk_action_result",
            "data": {
                "action": request.action,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        return result
    except Exception as e:
        logger.error(f"Error executing bulk action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/monitor/start")
async def start_monitoring(username: str = Depends(verify_token)):
    """Start DEADQ monitoring."""
    global monitor_task
    if not monitor.monitoring:
        if not monitor.connected:
            await monitor.initialize()
        monitor_task = asyncio.create_task(monitor.start_monitoring())
        return {"status": "started", "message": "DEADQ monitoring started"}
    return {"status": "already_running", "message": "Monitoring is already active"}


@app.post("/api/monitor/stop")
async def stop_monitoring(username: str = Depends(verify_token)):
    """Stop DEADQ monitoring."""
    global monitor_task


class CapacityThresholdRequest(BaseModel):
    threshold: int


@app.post("/api/capacity/threshold")
async def set_capacity_threshold(request: CapacityThresholdRequest, username: str = Depends(verify_token)):
    """Set the capacity monitoring threshold percentage."""
    if not (50 <= request.threshold <= 100):
        raise HTTPException(
            status_code=400,
            detail="Threshold must be between 50 and 100"
        )
    
    if monitor.set_capacity_threshold(request.threshold):
        return {
            "status": "success",
            "message": f"Capacity threshold set to {request.threshold}%",
            "threshold": request.threshold
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid threshold value")


@app.get("/api/capacity/status")
async def get_capacity_status(username: str = Depends(verify_token)):
    """Get current capacity monitoring status."""
    return {
        "monitoring": monitor.capacity_monitoring,
        "threshold": monitor.capacity_threshold,
        "poll_interval": monitor.capacity_poll_interval,
        "tracked_queues": len(monitor.tracked_queues)
    }

    if monitor.monitoring:
        await monitor.stop_monitoring()
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        return {"status": "stopped", "message": "DEADQ monitoring stopped"}
    return {"status": "not_running", "message": "Monitoring is not active"}


class AutoResolveToggleRequest(BaseModel):
    enabled: bool


@app.post("/api/auto-resolve/toggle")
async def toggle_auto_resolve(request: AutoResolveToggleRequest, username: str = Depends(verify_token)):
    """Toggle auto-resolve on/off."""
    try:
        result = monitor.toggle_auto_resolve(request.enabled)
        
        # Broadcast auto-resolve status change to all connected clients
        await ws_manager.broadcast({
            "type": "auto_resolve_status",
            "data": {
                "enabled": result["enabled"],
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        return result
    except Exception as e:
        logger.error(f"Error toggling auto-resolve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auto-resolve/status")
async def get_auto_resolve_status(username: str = Depends(verify_token)):
    """Get current auto-resolve status and configuration."""
    try:
        return monitor.get_auto_resolve_status()
    except Exception as e:
        logger.error(f"Error getting auto-resolve status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auto-resolve/audit-log")
async def get_auto_resolve_audit_log(username: str = Depends(verify_token)):
    """Get the auto-resolve audit log (most recent first)."""
    try:
        return {
            "status": "success",
            "audit_log": monitor.get_auto_resolve_audit_log()
        }
    except Exception as e:
        logger.error(f"Error getting auto-resolve audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alerts.
    Clients connect here to receive proactive notifications.
    """
    await ws_manager.connect(websocket)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "Connected to MQ Diagnostic Agent",
                "monitoring": monitor.monitoring,
                "deadq_name": monitor.deadq_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle client messages (e.g., ping/pong)
            if message.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


# Made with Bob