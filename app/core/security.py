import hmac
import hashlib
import time
import json
import sqlite3
from config import Config


class SecurityManager:
    """Security manager for signature verification"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
    
    def verify_signature_v151(self, node_id, payload, signature, timestamp, nonce):
        """
        Verify signature according to ANP v1.5.1
        
        Parameters:
            node_id: Node identifier
            payload: Dict or string payload
            signature: HMAC-SHA256 signature (hex)
            timestamp: Unix timestamp (int or string)
            nonce: Unique nonce string
            
        Returns:
            (bool, str): (is_valid, reason)
        """
        # Get secret key for this node
        secret_key = Config.VALID_NODE_IDS.get(node_id)
        if not secret_key:
            return False, f"Unknown Node ID: {node_id}"
        
        # Validate timestamp
        try:
            now = int(time.time())
            ts = int(timestamp)
            drift = abs(now - ts)
            if drift > 300:  # 5 minutes
                return False, f"Timestamp drift too high: {drift}s"
        except Exception as e:
            return False, f"Invalid timestamp format: {str(e)}"
        
        # Prepare payload string
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        else:
            payload_str = str(payload)
        
        # Construct base string per ANP v1.5.1
        base_string = f"{timestamp}.{nonce}.{node_id}.{payload_str}"
        
        # Calculate expected signature
        try:
            expected_sig = hmac.new(
                secret_key.encode('utf-8'),
                base_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest().lower()
            
            # Constant-time comparison
            if hmac.compare_digest(expected_sig, signature.lower()):
                return True, "Signature verified"
            else:
                return False, "Signature mismatch"
                
        except Exception as e:
            return False, f"Signature error: {str(e)}"