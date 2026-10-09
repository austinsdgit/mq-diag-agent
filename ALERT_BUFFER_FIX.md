# Alert Buffer Fix - DEADQ Showing Messages After Queue is Clear

## Problem Description

The mq-diag-agent was showing messages in the UI even after the DEADQ was cleared. This created confusion where:
- Direct queue inspection showed DEADQ was empty (depth = 0)
- The mq-diag-agent UI still displayed alert messages

## Root Cause

The issue was caused by two persistent data structures that were not being cleaned up:

1. **Alert Buffer** (`WebSocketManager.alert_buffer` in `main.py`):
   - Stores the last 100 alerts for replay to newly connected clients
   - Messages remained in buffer even after being removed from the queue
   - When reconnecting to the UI, all buffered alerts were replayed

2. **Alerted Messages Set** (`DeadQueueMonitor.alerted_messages` in `monitor.py`):
   - Tracks message IDs that have been alerted on to prevent duplicate alerts
   - Never cleared when messages were removed from the queue
   - Prevented re-alerting if the same message appeared again

## Solution Implemented

### 1. Clear Buffers When Queue is Empty
In `monitor.py`, the `check_deadq()` method now:
- Detects when the queue depth is 0
- Clears the `alerted_messages` set
- Clears the `alert_buffer` in the WebSocket handler
- Logs the cleanup action

```python
# If queue is empty, clear the alerted messages set
if current_depth == 0 and self.alerted_messages:
    logger.info(f"DEADQ is empty, clearing {len(self.alerted_messages)} alerted message IDs")
    self.alerted_messages.clear()
    # Also clear the alert buffer in the websocket handler
    if self.websocket_handler:
        self.websocket_handler.alert_buffer.clear()
        logger.info("Alert buffer cleared")
```

### 2. Remove Alerts When Messages are Deleted
In `monitor.py`, the `execute_action()` method now:
- Removes the specific message from the alert buffer when deleted
- Ensures the UI doesn't show stale alerts

```python
# Remove from alert buffer
if self.websocket_handler:
    self.websocket_handler.alert_buffer = [
        alert for alert in self.websocket_handler.alert_buffer
        if alert.get('data', {}).get('message_id') != message_id
    ]
    logger.info(f"Removed message {message_id} from alert buffer")
```

## Testing

To verify the fix:

1. **Send a test message to DEADQ**:
   ```bash
   ./send-test-message.sh
   ```

2. **Verify alert appears in UI**:
   - Check that the mq-diag-agent UI shows the alert
   - Note the message ID

3. **Clear the DEADQ**:
   ```bash
   # Use MQ console or command to clear the queue
   ```

4. **Verify cleanup**:
   - Check logs for "DEADQ is empty, clearing X alerted message IDs"
   - Check logs for "Alert buffer cleared"
   - Refresh the UI - alerts should be gone

5. **Reconnect to UI**:
   - Close and reopen the browser
   - Verify no stale alerts are replayed

## Benefits

- **Accurate State**: UI now reflects the actual queue state
- **No Stale Alerts**: Old alerts are automatically cleaned up
- **Proper Reconnection**: New connections don't see old, resolved alerts
- **Better UX**: Users can trust the UI to show current issues only

## Files Modified

- `mq-diag-agent/backend/monitor.py`: Added cleanup logic in `check_deadq()` and `execute_action()`

## Date
2026-05-27