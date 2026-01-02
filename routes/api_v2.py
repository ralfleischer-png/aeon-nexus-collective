from flask import Blueprint, request, jsonify, g
import time
import json
import hashlib
from datetime import datetime
from config import Config

api_v2_bp = Blueprint("api_v2", __name__, url_prefix="/api/v2")


def _get_node_id():
    return (
        request.headers.get("X-AEON-Node-ID")
        or request.headers.get("X-AEON-INSTANCE-ID")
        or ""
    )


@api_v2_bp.route("/status", methods=["GET"])
def status():
    """Enhanced status endpoint with stats - JSON ONLY"""
    try:
        db = g.get("db_manager")
        
        conn = db.get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM aeon_log_chain").fetchone()
            log_count = row["cnt"] if row and row["cnt"] else 0
            
            mem_row = conn.execute("SELECT COUNT(*) AS cnt FROM aeon_collective_memory").fetchone()
            memory_count = mem_row["cnt"] if mem_row and mem_row["cnt"] else 0
            
            prop_row = conn.execute("SELECT COUNT(*) AS cnt FROM aeon_collective_proposals").fetchone()
            proposal_count = prop_row["cnt"] if prop_row and prop_row["cnt"] else 0
        finally:
            conn.close()
        
        return jsonify({
            "status": "OPERATIONAL",
            "protocol": f"ANP v{Config.SIGNATURE_VERSION}",
            "version": "3.5.1",
            "timestamp": int(time.time()),
            "log_entries": log_count,
            "memory_count": memory_count,
            "proposal_count": proposal_count,
            "note": "For HTML interface visit /admin/ui/chain or /admin/ui/memory"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v2_bp.route("/events", methods=["POST"])
def append_event():
    """Append event to log chain - requires signature"""
    try:
        signature = request.headers.get("X-AEON-Signature", "")
        timestamp = request.headers.get("X-AEON-Timestamp", "")
        nonce = request.headers.get("X-AEON-Nonce", "")
        node_id = _get_node_id()

        if not all([signature, timestamp, nonce, node_id]):
            return jsonify({"status": "ERROR", "error": "Missing signature headers"}), 400

        try:
            payload = request.get_json(force=True)
        except Exception as e:
            return jsonify({"status": "ERROR", "error": f"Invalid JSON: {e}"}), 400

        security = g.get("security_manager")
        if not security:
            return jsonify({"status": "ERROR", "error": "Security not initialized"}), 500

        valid, reason = security.verify_signature_v151(node_id, payload, signature, timestamp, nonce)
        if not valid:
            return jsonify({"status": "SIGNATURE_REJECTED", "error": reason}), 401

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
                payload.get("type", "EVENT"),
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
            "status": "EVENT_ACCEPTED",
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


@api_v2_bp.route("/memories", methods=["GET"])
def list_memories():
    """List collective memories with filtering - JSON ONLY"""
    try:
        db = g.get("db_manager")
        agent_id = request.args.get("agent_id", "")
        insight_type = request.args.get("type", "")

        try:
            limit = min(int(request.args.get("limit", 100)), 1000)
        except Exception:
            limit = 100

        query = "SELECT * FROM aeon_collective_memory WHERE 1=1"
        params = []

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if insight_type:
            query += " AND insight_type = ?"
            params.append(insight_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = db.get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            memories = [dict(r) for r in rows]
            
            count_query = "SELECT COUNT(*) as cnt FROM aeon_collective_memory WHERE 1=1"
            count_params = []
            if agent_id:
                count_query += " AND agent_id = ?"
                count_params.append(agent_id)
            if insight_type:
                count_query += " AND insight_type = ?"
                count_params.append(insight_type)
            
            total_row = conn.execute(count_query, count_params).fetchone()
            total = total_row["cnt"] if total_row else 0
        finally:
            conn.close()
        
        return jsonify({
            "status": "SUCCESS",
            "count": len(memories),
            "total": total,
            "limit": limit,
            "filters": {
                "agent_id": agent_id or None,
                "type": insight_type or None
            },
            "memories": memories,
            "note": "For HTML interface visit /admin/ui/memory"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@api_v2_bp.route("/", methods=["GET"])
def api_v2_index():
    """API v2 documentation page - JSON ONLY"""
    try:
        return jsonify({
            "status": "OPERATIONAL",
            "api_version": "v2",
            "protocol": f"ANP v{Config.SIGNATURE_VERSION}",
            "version": "3.5.1",
            "timestamp": int(time.time()),
            "features": [
                "Enhanced status endpoint with comprehensive statistics",
                "Event-based log chain entries",
                "Advanced memory filtering by agent and type",
                "Improved JSON responses with metadata"
            ],
            "endpoints": {
                "/api/v2/": "API v2 documentation (this page)",
                "/api/v2/status": "System status with statistics",
                "/api/v2/memories": "List collective memories (supports filtering)",
                "/api/v2/events": "Append event to log chain (POST, requires signature)"
            },
            "note": "For HTML interface visit /admin/ui/chain or /admin/ui/memory"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": int(time.time())
        }), 500