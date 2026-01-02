from flask import Blueprint, request, jsonify, g
import time
import json
import hashlib
from config import Config

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _get_node_id():
    """Accept both X-AEON-Node-ID and X-AEON-INSTANCE-ID."""
    return (
        request.headers.get("X-AEON-Node-ID")
        or request.headers.get("X-AEON-INSTANCE-ID")
        or ""
    )


@api_v1_bp.route("/health", methods=["GET"])
def health_v1():
    """API v1 Health check endpoint - JSON ONLY"""
    try:
        db = g.get("db_manager")
        
        # Test database
        db_status = "disconnected"
        try:
            conn = db.get_connection()
            conn.execute("SELECT 1")
            conn.close()
            db_status = "connected"
        except Exception:
            pass
        
        return jsonify({
            "status": "OPERATIONAL",
            "api_version": "v1",
            "protocol": f"ANP v{Config.SIGNATURE_VERSION}",
            "database": db_status,
            "timestamp": int(time.time()),
            "note": "For HTML interface visit /api/v2/status or /admin/ui/chain"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v1_bp.route("/status", methods=["GET"])
def status_v1():
    """API v1 Status endpoint - alias for health - JSON ONLY"""
    return health_v1()


@api_v1_bp.route("/protocol", methods=["GET"])
def protocol_info():
    """Protocol information endpoint - JSON ONLY"""
    try:
        return jsonify({
            "status": "OPERATIONAL",
            "protocol": f"ANP v{Config.SIGNATURE_VERSION}",
            "version": "3.5.1",
            "timestamp": int(time.time()),
            "documentation": {
                "signature_headers": [
                    "X-AEON-Signature",
                    "X-AEON-Timestamp", 
                    "X-AEON-Nonce",
                    "X-AEON-Node-ID"
                ],
                "signature_format": "HMAC-SHA256(secret_key, 'timestamp.nonce.node_id.canonical_json')",
                "endpoints": {
                    "/api/v1/protocol": "Protocol information (this page)",
                    "/api/v1/health": "Health check",
                    "/api/v1/chain": "Get log chain entries",
                    "/api/v1/persist": "Persist entry (requires signature)",
                    "/api/v1/memory": "Query collective memory"
                }
            },
            "note": "For HTML interface with full docs, visit /api/v2/status or /admin/ui/chain"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v1_bp.route("/persist", methods=["POST"])
def persist():
    """Persist entry to log chain - requires signature"""
    try:
        signature = request.headers.get("X-AEON-Signature", "")
        timestamp = request.headers.get("X-AEON-Timestamp", "")
        nonce = request.headers.get("X-AEON-Nonce", "")
        node_id = _get_node_id()

        if not all([signature, timestamp, nonce, node_id]):
            return jsonify({
                "status": "ERROR",
                "error": "Missing signature headers",
                "required": [
                    "X-AEON-Signature",
                    "X-AEON-Timestamp",
                    "X-AEON-Nonce",
                    "X-AEON-Node-ID or X-AEON-INSTANCE-ID"
                ]
            }), 400

        try:
            payload = request.get_json(force=True)
        except Exception as e:
            return jsonify({"status": "ERROR", "error": f"Invalid JSON: {e}"}), 400

        security = g.get("security_manager")
        if not security:
            return jsonify({"status": "ERROR", "error": "Security not initialized"}), 500

        valid, reason = security.verify_signature_v151(node_id, payload, signature, timestamp, nonce)
        if not valid:
            return jsonify({
                "status": "SIGNATURE_REJECTED",
                "error": reason,
                "protocol": Config.SIGNATURE_VERSION
            }), 401

        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        db = g.get("db_manager")

        conn = db.get_connection()
        try:
            last = conn.execute(
                "SELECT current_hash FROM aeon_log_chain ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = last["current_hash"] if last else "0" * 64

            ts_int = int(timestamp)
            entry_id = hashlib.sha256(
                f"{node_id}:{ts_int}:{canonical_json}".encode("utf-8")
            ).hexdigest()[:24]

            entry_core = {
                "prev": prev_hash,
                "ts": ts_int,
                "node": node_id,
                "payload": json.loads(canonical_json),
                "entry_id": entry_id
            }

            current_hash = hashlib.sha256(
                json.dumps(entry_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

            now = int(time.time())
            conn.execute("""
                INSERT INTO aeon_log_chain
                (entry_id, node_id, operation, payload_json,
                 previous_hash, current_hash, signature, timestamp, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id,
                node_id,
                payload.get("op", "PERSIST"),
                canonical_json,
                prev_hash,
                current_hash,
                signature,
                ts_int,
                "COMMITTED",
                now
            ))
            conn.commit()
        finally:
            conn.close()

        return jsonify({
            "status": "SUCCESS",
            "entry_id": entry_id,
            "current_hash": current_hash,
            "prev_hash": prev_hash
        }), 201
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v1_bp.route("/memory", methods=["GET"])
def memory_v1():
    """Query collective memory - JSON ONLY"""
    try:
        db = g.get("db_manager")
        instance_id = request.args.get("instance", "")

        if not instance_id:
            return jsonify({
                "status": "ERROR",
                "error": "Missing 'instance' query parameter",
                "usage": "/api/v1/memory?instance=NODE_ID&limit=100"
            }), 400

        try:
            limit = min(int(request.args.get("limit", 100)), 1000)
        except Exception:
            limit = 100

        conn = db.get_connection()
        try:
            rows = conn.execute(
                """
                SELECT * FROM aeon_collective_memory
                WHERE agent_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (instance_id, limit)
            ).fetchall()
            
            memories = [dict(r) for r in rows]
        finally:
            conn.close()

        return jsonify({
            "status": "SUCCESS",
            "instance": instance_id,
            "count": len(memories),
            "memories": memories
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v1_bp.route("/chain", methods=["GET"])
def get_chain():
    """Get log chain entries - JSON ONLY"""
    try:
        db = g.get("db_manager")
        
        try:
            limit = min(int(request.args.get("limit", 50)), 500)
            offset = max(int(request.args.get("offset", 0)), 0)
        except Exception:
            limit = 50
            offset = 0
        
        conn = db.get_connection()
        try:
            rows = conn.execute("""
                SELECT entry_id, node_id, operation, timestamp, 
                       current_hash, previous_hash, state
                FROM aeon_log_chain
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
            
            entries = [dict(r) for r in rows]
        finally:
            conn.close()
        
        return jsonify({
            "status": "SUCCESS",
            "count": len(entries),
            "limit": limit,
            "offset": offset,
            "entries": entries,
            "note": "For HTML interface visit /admin/ui/chain"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500