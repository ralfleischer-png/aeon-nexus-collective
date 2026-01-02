#!/usr/bin/env python3
"""
AEON NEXUS Consensus Engine - Health Check
==========================================
Check the health and status of the consensus engine.

Usage:
    python health_check.py [db_path]
    
Example:
    python health_check.py /home/superral/aeon_nexus/data/aeon.db
    
Returns:
    0 if healthy
    1 if unhealthy
"""

import sqlite3
import json
import time
import sys
from datetime import datetime, timedelta

def check_database_health(db_path: str) -> dict:
    """Check database connectivity and integrity"""
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        # Check integrity
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "accessible": True,
            "integrity": integrity,
            "error": None
        }
        
    except Exception as e:
        return {
            "accessible": False,
            "integrity": None,
            "error": str(e)
        }

def check_consensus_health(db_path: str) -> dict:
    """Check consensus engine health"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        now = int(time.time())
        
        # Count pending expired proposals
        cursor.execute("""
            SELECT COUNT(*) 
            FROM aeon_collective_proposals 
            WHERE status = 'VOTING_OPEN' 
            AND expires_at <= ?
            AND (evaluated_at IS NULL OR evaluated_at = 0)
        """, (now,))
        pending_proposals = cursor.fetchone()[0]
        
        # Count active nodes
        cursor.execute("""
            SELECT COUNT(*) 
            FROM aeon_nodes 
            WHERE status = 'ACTIVE'
        """)
        active_nodes = cursor.fetchone()[0]
        
        # Count total proposals by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM aeon_collective_proposals
            GROUP BY status
        """)
        proposals_by_status = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # Get recent decisions (last 24 hours)
        yesterday = now - 86400
        cursor.execute("""
            SELECT COUNT(*)
            FROM aeon_consensus_log
            WHERE event_type = 'PROPOSAL_DECIDED'
            AND timestamp > ?
        """, (yesterday,))
        recent_decisions = cursor.fetchone()[0]
        
        # Check for stuck proposals (expired >1 hour ago but not evaluated)
        one_hour_ago = now - 3600
        cursor.execute("""
            SELECT COUNT(*)
            FROM aeon_collective_proposals
            WHERE status = 'VOTING_OPEN'
            AND expires_at < ?
            AND (evaluated_at IS NULL OR evaluated_at = 0)
        """, (one_hour_ago,))
        stuck_proposals = cursor.fetchone()[0]
        
        # Get last evaluation time
        cursor.execute("""
            SELECT MAX(evaluated_at)
            FROM aeon_collective_proposals
            WHERE evaluated_at IS NOT NULL
        """)
        last_eval = cursor.fetchone()[0]
        
        conn.close()
        
        # Determine health status
        is_healthy = stuck_proposals == 0
        
        return {
            "healthy": is_healthy,
            "pending_proposals": pending_proposals,
            "stuck_proposals": stuck_proposals,
            "active_nodes": active_nodes,
            "proposals_by_status": proposals_by_status,
            "recent_decisions_24h": recent_decisions,
            "last_evaluation": last_eval,
            "last_evaluation_ago": (now - last_eval) if last_eval else None,
            "timestamp": now
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "timestamp": int(time.time())
        }

def format_health_report(db_health: dict, consensus_health: dict, verbose: bool = False) -> str:
    """Format health check results as readable report"""
    
    lines = []
    lines.append("=" * 70)
    lines.append("AEON NEXUS Consensus Engine - Health Check")
    lines.append("=" * 70)
    lines.append("")
    
    # Database Health
    lines.append("DATABASE:")
    if db_health['accessible']:
        lines.append(f"  ✓ Accessible")
        lines.append(f"  ✓ Integrity: {db_health['integrity']}")
    else:
        lines.append(f"  ✗ NOT ACCESSIBLE")
        lines.append(f"    Error: {db_health['error']}")
    lines.append("")
    
    # Overall Health
    if consensus_health.get('healthy'):
        lines.append("STATUS: ✓ HEALTHY")
    else:
        lines.append("STATUS: ✗ UNHEALTHY")
        if consensus_health.get('error'):
            lines.append(f"  Error: {consensus_health['error']}")
    lines.append("")
    
    # Metrics
    if 'pending_proposals' in consensus_health:
        lines.append("METRICS:")
        lines.append(f"  Pending expired proposals: {consensus_health['pending_proposals']}")
        lines.append(f"  Stuck proposals (>1hr): {consensus_health['stuck_proposals']}")
        lines.append(f"  Active nodes: {consensus_health['active_nodes']}")
        lines.append(f"  Recent decisions (24h): {consensus_health['recent_decisions_24h']}")
        
        if consensus_health['last_evaluation']:
            ago = consensus_health['last_evaluation_ago']
            if ago < 3600:
                ago_str = f"{ago // 60} minutes ago"
            elif ago < 86400:
                ago_str = f"{ago // 3600} hours ago"
            else:
                ago_str = f"{ago // 86400} days ago"
            lines.append(f"  Last evaluation: {ago_str}")
        else:
            lines.append(f"  Last evaluation: Never")
        
        lines.append("")
    
    # Detailed Stats (verbose mode)
    if verbose and 'proposals_by_status' in consensus_health:
        lines.append("PROPOSAL STATUS BREAKDOWN:")
        for status, count in consensus_health['proposals_by_status'].items():
            lines.append(f"  {status}: {count}")
        lines.append("")
    
    # Warnings
    if consensus_health.get('stuck_proposals', 0) > 0:
        lines.append("⚠️  WARNINGS:")
        lines.append(f"  {consensus_health['stuck_proposals']} proposals stuck for >1 hour")
        lines.append("  Consensus engine may not be running!")
        lines.append("")
    
    # Timestamp
    ts = consensus_health.get('timestamp', int(time.time()))
    lines.append(f"Checked at: {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    
    return "\n".join(lines)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check AEON NEXUS Consensus Engine Health'
    )
    
    parser.add_argument('db_path', nargs='?',
                       default='/home/superral/aeon_nexus/data/aeon.db',
                       help='Path to database')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    # Run health checks
    db_health = check_database_health(args.db_path)
    consensus_health = check_consensus_health(args.db_path)
    
    # Determine overall health
    is_healthy = (
        db_health['accessible'] and 
        db_health['integrity'] == 'ok' and
        consensus_health.get('healthy', False)
    )
    
    if args.json:
        # JSON output
        output = {
            "overall": "healthy" if is_healthy else "unhealthy",
            "database": db_health,
            "consensus": consensus_health
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        report = format_health_report(db_health, consensus_health, args.verbose)
        print(report)
    
    # Exit code
    return 0 if is_healthy else 1

if __name__ == "__main__":
    sys.exit(main())
