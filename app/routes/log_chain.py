from flask import Blueprint, request, jsonify, g
import time
import json
import hashlib

log_bp = Blueprint("log_chain", __name__)

@log_bp.route("/log", methods=["POST"])
def append_log():
    """Append to hash chain."""
    # Get headers
    signature = request.headers.get("X-AEON-Signature", "")
    timestamp = request.headers.get("X-AEON-Timestamp", "")
    nonce = request.headers.get("X-AEON-Nonce", "")
    node_id = request.headers.get("X-AEON-Node-ID", "")
    
    if not all([signature, timestamp, nonce, node_id]):
        return jsonify({"status": "ERROR", "error": "Missing headers"}), 400
    
    # Get payload
    try:
        payload = request.get_json(force=True)
    except:
        return jsonify({"status": "ERROR", "error": "Invalid JSON"}), 400
    
    # Verify signature
    security = g.get("security_manager")
    if not security:
        return jsonify({"status": "ERROR", "error": "Security not available"}), 500
    
    # Call with correct parameter order
    valid, reason = security.verify_signature_v151(
        node_id, payload, signature, timestamp, nonce
    )
    
    if not valid:
        return jsonify({"status": "SIGNATURE_REJECTED", "error": reason}), 401
    
    # Continue with log append...
    db = g.get("db_manager")
    try:
        with db.get_connection() as conn:
            # Get last hash
            last = conn.execute(
                "SELECT current_hash FROM aeon_log_chain ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = last["current_hash"] if last else "0" * 64
            
            # Create entry
            ts_int = int(timestamp)
            canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            
            entry_id = hashlib.sha256(
                f"{node_id}:{ts_int}:{canonical_json}".encode()
            ).hexdigest()[:24]
            
            # Calculate current hash
            current_hash = hashlib.sha256(
                f"{prev_hash}{entry_id}{canonical_json}{ts_int}".encode()
            ).hexdigest()
            
            # Insert
            conn.execute("""
                INSERT INTO aeon_log_chain
                (entry_id, node_id, operation, payload_json,
                 previous_hash, current_hash, signature, timestamp, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id,
                node_id,
                payload.get("op", "LOG"),
                canonical_json,
                prev_hash,
                current_hash,
                signature,
                ts_int,
                "COMMITTED",
                int(time.time())
            ))
            
            conn.commit()
            
        return jsonify({
            "status": "SUCCESS",
            "entry_id": entry_id,
            "current_hash": current_hash,
            "prev_hash": prev_hash
        }), 201
        
    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500

@log_bp.route("/log", methods=["GET"])
def get_logs():
    """Get recent log entries."""
    db = g.get("db_manager")
    try:
        limit = min(int(request.args.get("limit", 50)), 1000)
    except:
        limit = 50
    
    try:
        with db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM aeon_log_chain ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            
        return jsonify({
            "status": "SUCCESS",
            "count": len(rows),
            "entries": [dict(r) for r in rows]
        }), 200
    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500