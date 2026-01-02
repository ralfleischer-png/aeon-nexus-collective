from flask import Blueprint, jsonify, g
import time

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/health", methods=["GET"])
def health():
    db = g.get("db_manager")
    with db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) AS cnt FROM aeon_log_chain")
        row = cur.fetchone()
        log_count = row["cnt"] if row else 0

    return jsonify({
        "status": "OPERATIONAL",
        "version": "3.5.1",
        "protocol": "ANP",
        "timestamp": int(time.time()),
        "log_entries": log_count
    }), 200


@admin_bp.route("/chain/summary", methods=["GET"])
def chain_summary():
    db = g.get("db_manager")
    with db.get_connection() as conn:
        cur = conn.execute("""
            SELECT id, entry_id, node_id, previous_hash, current_hash, timestamp, state
            FROM aeon_log_chain
            ORDER BY id DESC
            LIMIT 50
        """)
        rows = cur.fetchall()
        result = [dict(r) for r in rows]
    return jsonify({
        "status": "SUCCESS",
        "count": len(result),
        "entries": result
    }), 200
