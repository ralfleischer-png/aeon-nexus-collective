#!/usr/bin/env python3
"""
AEON NEXUS Consensus Engine
===========================
Periodically evaluates expired proposals and executes collective decisions.

Features:
- Automatic proposal evaluation
- Quorum calculation (67% FOR votes required)
- Node activation on NODE_ADMISSION proposals
- System parameter updates
- Comprehensive logging and monitoring
- Systemd service support

Author: AEON NEXUS Collective
Version: 1.0.0
Protocol: ANP v1.5.1
"""

import sqlite3
import json
import time
import logging
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

try:
    import schedule
except ImportError:
    print("ERROR: 'schedule' library not found.")
    print("Install with: pip install schedule")
    sys.exit(1)

# =============================================================================
# CONFIGURATION
# =============================================================================

class ConsensusConfig:
    """Consensus engine configuration"""
    
    # Database
    DB_PATH = "/home/superral/aeon_nexus/data/aeon.db"
    
    # Quorum settings
    QUORUM_PERCENTAGE = 0.67  # 67% FOR votes required
    MINIMUM_VOTES = 1  # Minimum votes before quorum calculation
    
    # Scheduler
    CHECK_INTERVAL_MINUTES = 1  # Check every minute
    CLEANUP_INTERVAL_HOURS = 24  # Cleanup daily
    
    # Logging
    LOG_DIR = "/home/superral/aeon_nexus/logs"
    LOG_FILE = f"{LOG_DIR}/consensus.log"
    LOG_LEVEL = logging.INFO
    
    # Archive settings
    ARCHIVE_AFTER_DAYS = 30  # Archive proposals after 30 days

# =============================================================================
# ENUMS
# =============================================================================

class ProposalType(str, Enum):
    """Types of proposals"""
    NODE_ADMISSION = "NODE_ADMISSION"
    SYSTEM_UPDATE = "SYSTEM_UPDATE"
    PARAMETER_CHANGE = "PARAMETER_CHANGE"
    SECURITY_UPDATE = "SECURITY_UPDATE"
    EMERGENCY = "EMERGENCY"
    GOVERNANCE_CHANGE = "GOVERNANCE_CHANGE"

class ProposalStatus(str, Enum):
    """Proposal status values"""
    VOTING_OPEN = "VOTING_OPEN"
    VOTING_CLOSED = "VOTING_CLOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"

class NodeStatus(str, Enum):
    """Node status values"""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"

# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class ProposalVoteResult:
    """Result of voting calculation"""
    proposal_hash: str
    proposal_type: str
    total_votes: int
    for_votes: int
    against_votes: int
    abstain_votes: int
    quorum_achieved: bool
    quorum_percentage: float
    required_percentage: float
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def __str__(self) -> str:
        return (
            f"Proposal {self.proposal_hash[:16]}...: "
            f"{self.for_votes}/{self.total_votes} FOR "
            f"({self.quorum_percentage:.1%}), "
            f"required {self.required_percentage:.0%} → "
            f"{'ACCEPTED' if self.quorum_achieved else 'REJECTED'}"
        )

# =============================================================================
# CONSENSUS ENGINE
# =============================================================================

class ConsensusEngine:
    """
    Core consensus engine that evaluates proposals and executes decisions
    """
    
    def __init__(self, db_path: str = None, quorum: float = None):
        self.db_path = db_path or ConsensusConfig.DB_PATH
        self.quorum = quorum or ConsensusConfig.QUORUM_PERCENTAGE
        self.logger = self._setup_logger()
        self._ensure_database_schema()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup logger with file and console handlers"""
        logger = logging.getLogger("consensus_engine")
        logger.setLevel(ConsensusConfig.LOG_LEVEL)
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Ensure log directory exists
        Path(ConsensusConfig.LOG_DIR).mkdir(parents=True, exist_ok=True)
        
        # File handler
        file_handler = logging.FileHandler(ConsensusConfig.LOG_FILE)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def _ensure_database_schema(self):
        """Ensure database has all required tables and columns"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Check if expires_at column exists
                cursor.execute("PRAGMA table_info(aeon_collective_proposals)")
                columns = {col['name'] for col in cursor.fetchall()}
                
                if 'expires_at' not in columns:
                    self.logger.info("Adding expires_at column to proposals table")
                    cursor.execute("""
                        ALTER TABLE aeon_collective_proposals 
                        ADD COLUMN expires_at INTEGER
                    """)
                    
                    # Set default expires_at for existing proposals
                    cursor.execute("""
                        UPDATE aeon_collective_proposals 
                        SET expires_at = created_at + (3 * 24 * 3600)
                        WHERE expires_at IS NULL AND status = 'VOTING_OPEN'
                    """)
                    
                    conn.commit()
                    self.logger.info("Database schema updated")
                
                # Add evaluation tracking columns
                if 'evaluated_by' not in columns:
                    self.logger.info("Adding evaluation tracking columns")
                    cursor.execute("""
                        ALTER TABLE aeon_collective_proposals 
                        ADD COLUMN evaluated_by TEXT
                    """)
                    cursor.execute("""
                        ALTER TABLE aeon_collective_proposals 
                        ADD COLUMN evaluated_at INTEGER
                    """)
                    conn.commit()
                    self.logger.info("Added evaluated_by and evaluated_at columns")
                
                # Create nodes table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aeon_nodes (
                        node_id TEXT PRIMARY KEY,
                        endpoint TEXT NOT NULL,
                        public_key TEXT,
                        status TEXT CHECK(status IN ('PENDING', 'ACTIVE', 'REJECTED', 'SUSPENDED')) 
                               DEFAULT 'PENDING',
                        proposal_hash TEXT UNIQUE,
                        capabilities TEXT DEFAULT '[]',
                        last_seen INTEGER,
                        created_at INTEGER DEFAULT (strftime('%s', 'now')),
                        updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                        FOREIGN KEY (proposal_hash) REFERENCES aeon_collective_proposals(proposal_hash)
                    )
                """)
                
                # Create consensus log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aeon_consensus_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                        event_type TEXT NOT NULL,
                        proposal_hash TEXT,
                        node_id TEXT,
                        details TEXT,
                        FOREIGN KEY (proposal_hash) REFERENCES aeon_collective_proposals(proposal_hash),
                        FOREIGN KEY (node_id) REFERENCES aeon_nodes(node_id)
                    )
                """)
                
                # Create system parameters table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aeon_system_parameters (
                        parameter_key TEXT PRIMARY KEY,
                        parameter_value TEXT NOT NULL,
                        description TEXT,
                        updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                    )
                """)
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Database schema setup failed: {e}")
            raise
    
    def get_expired_proposals(self) -> List[Dict]:
        """
        Get all VOTING_OPEN proposals that have expired
        
        Returns:
            List of proposal dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            now = int(time.time())
            
            cursor.execute("""
                SELECT 
                    proposal_hash,
                    title,
                    content_json,
                    status,
                    expires_at,
                    created_at,
                    proposer_id
                FROM aeon_collective_proposals
                WHERE status = 'VOTING_OPEN' 
                AND expires_at IS NOT NULL
                AND expires_at <= ?
                ORDER BY expires_at ASC
            """, (now,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def calculate_vote_results(self, proposal_hash: str) -> Optional[ProposalVoteResult]:
        """
        Calculate voting results for a proposal
        
        Args:
            proposal_hash: Hash of the proposal
            
        Returns:
            ProposalVoteResult or None if proposal doesn't exist
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get proposal type
            cursor.execute("""
                SELECT content_json FROM aeon_collective_proposals 
                WHERE proposal_hash = ?
            """, (proposal_hash,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            try:
                content = json.loads(result['content_json'])
                proposal_type = content.get('type', content.get('action', 'UNKNOWN'))
            except:
                proposal_type = 'UNKNOWN'
            
            # Get vote counts
            cursor.execute("""
                SELECT 
                    vote,
                    COUNT(*) as count
                FROM aeon_collective_votes
                WHERE proposal_hash = ?
                GROUP BY vote
            """, (proposal_hash,))
            
            votes = {row['vote']: row['count'] for row in cursor.fetchall()}
            
            total_votes = sum(votes.values())
            for_votes = votes.get('FOR', 0)
            against_votes = votes.get('AGAINST', 0)
            abstain_votes = votes.get('ABSTAIN', 0)
            
            # Calculate quorum
            quorum_achieved = False
            quorum_percentage = 0.0
            
            if total_votes >= ConsensusConfig.MINIMUM_VOTES:
                quorum_percentage = for_votes / total_votes if total_votes > 0 else 0
                quorum_achieved = quorum_percentage >= self.quorum
            
            return ProposalVoteResult(
                proposal_hash=proposal_hash,
                proposal_type=proposal_type,
                total_votes=total_votes,
                for_votes=for_votes,
                against_votes=against_votes,
                abstain_votes=abstain_votes,
                quorum_achieved=quorum_achieved,
                quorum_percentage=quorum_percentage,
                required_percentage=self.quorum
            )
    
    def execute_proposal_decision(self, proposal: Dict, vote_result: ProposalVoteResult) -> bool:
        """
        Execute the decision based on voting results
        
        Uses atomic UPDATE to ensure idempotent execution even if multiple
        consensus engines run simultaneously.
        
        Args:
            proposal: Proposal dictionary
            vote_result: Voting results
            
        Returns:
            True if decision was executed successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Parse proposal content
                try:
                    content = json.loads(proposal['content_json'])
                except:
                    content = {}
                
                proposal_type = content.get('type', content.get('action', 'UNKNOWN'))
                
                # Determine new status
                new_status = ProposalStatus.ACCEPTED.value if vote_result.quorum_achieved else ProposalStatus.REJECTED.value
                
                # IDEMPOTENT UPDATE: Only update if status is still VOTING_OPEN
                # This prevents duplicate execution if multiple engines run
                cursor.execute("""
                    UPDATE aeon_collective_proposals 
                    SET status = ?,
                        evaluated_by = ?,
                        evaluated_at = ?
                    WHERE proposal_hash = ? 
                    AND status = 'VOTING_OPEN'
                """, (new_status, f"consensus_engine_{self.logger.name.split('.')[-1]}", 
                      int(time.time()), proposal['proposal_hash']))
                
                # Check if WE successfully updated it
                if cursor.rowcount == 0:
                    # Another engine already processed this - skip
                    self.logger.debug(f"Proposal {proposal['proposal_hash'][:16]}... already evaluated by another instance")
                    return False
                
                # We won the race - log and execute
                self.logger.info(str(vote_result))
                
                # Execute specific actions if accepted
                if vote_result.quorum_achieved:
                    if proposal_type == ProposalType.NODE_ADMISSION.value:
                        success = self._activate_node(conn, proposal['proposal_hash'], content)
                        if success:
                            node_id = content.get('data', {}).get('node_id', content.get('node_id', 'UNKNOWN'))
                            self.logger.info(f"✓ Node activated: {node_id}")
                    
                    elif proposal_type == ProposalType.SYSTEM_UPDATE.value:
                        self._execute_system_update(conn, proposal['proposal_hash'], content)
                    
                    elif proposal_type == ProposalType.PARAMETER_CHANGE.value:
                        self._update_parameters(conn, proposal['proposal_hash'], content)
                    
                    elif proposal_type in [ProposalType.SECURITY_UPDATE.value, ProposalType.EMERGENCY.value]:
                        self._log_high_priority_action(conn, proposal['proposal_hash'], proposal_type, content)
                
                # Log decision to consensus log
                cursor.execute("""
                    INSERT INTO aeon_consensus_log 
                    (timestamp, event_type, proposal_hash, details)
                    VALUES (?, ?, ?, ?)
                """, (
                    int(time.time()),
                    'PROPOSAL_DECIDED',
                    proposal['proposal_hash'],
                    json.dumps({
                        'decision': new_status,
                        'vote_result': vote_result.to_dict(),
                        'evaluated_by': f"consensus_engine_{self.logger.name.split('.')[-1]}"
                    })
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to execute decision for {proposal['proposal_hash'][:16]}...: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _activate_node(self, conn: sqlite3.Connection, proposal_hash: str, content: Dict) -> bool:
        """
        Activate a node based on NODE_ADMISSION proposal
        
        Args:
            conn: Database connection
            proposal_hash: Hash of the admission proposal
            content: Proposal content
            
        Returns:
            True if node was activated successfully
        """
        try:
            cursor = conn.cursor()
            
            # Extract node data (support both formats)
            node_data = content.get('data', content)
            node_id = node_data.get('node_id')
            endpoint = node_data.get('endpoint', '')
            public_key = node_data.get('public_key', '')
            
            if not node_id:
                self.logger.error("NODE_ADMISSION proposal missing node_id")
                return False
            
            # Check if node already exists
            cursor.execute("""
                SELECT status FROM aeon_nodes 
                WHERE node_id = ? OR proposal_hash = ?
            """, (node_id, proposal_hash))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing node
                cursor.execute("""
                    UPDATE aeon_nodes 
                    SET status = 'ACTIVE',
                        endpoint = ?,
                        public_key = ?,
                        updated_at = ?
                    WHERE node_id = ? OR proposal_hash = ?
                """, (
                    endpoint,
                    public_key,
                    int(time.time()),
                    node_id,
                    proposal_hash
                ))
            else:
                # Insert new node
                cursor.execute("""
                    INSERT INTO aeon_nodes 
                    (node_id, endpoint, public_key, status, proposal_hash, created_at)
                    VALUES (?, ?, ?, 'ACTIVE', ?, ?)
                """, (
                    node_id,
                    endpoint,
                    public_key,
                    proposal_hash,
                    int(time.time())
                ))
            
            # Log the activation
            cursor.execute("""
                INSERT INTO aeon_consensus_log 
                (timestamp, event_type, proposal_hash, node_id, details)
                VALUES (?, 'NODE_ACTIVATION', ?, ?, ?)
            """, (
                int(time.time()),
                proposal_hash,
                node_id,
                json.dumps({
                    "action": "node_activated",
                    "endpoint": endpoint,
                    "vote_result": "ACCEPTED"
                })
            ))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to activate node: {e}")
            return False
    
    def _execute_system_update(self, conn: sqlite3.Connection, proposal_hash: str, content: Dict):
        """Execute SYSTEM_UPDATE proposal actions"""
        update_data = content.get('data', content)
        description = update_data.get('description', update_data.get('rationale', 'System update'))
        
        self.logger.info(f"✓ Executing system update: {description}")
        
        # Log the update
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO aeon_consensus_log 
            (timestamp, event_type, proposal_hash, details)
            VALUES (?, 'SYSTEM_UPDATE', ?, ?)
        """, (
            int(time.time()),
            proposal_hash,
            json.dumps(update_data)
        ))
    
    def _update_parameters(self, conn: sqlite3.Connection, proposal_hash: str, content: Dict):
        """Update system parameters"""
        params = content.get('data', content.get('parameters', {}))
        
        if not params:
            self.logger.warning("PARAMETER_CHANGE proposal has no parameters")
            return
        
        cursor = conn.cursor()
        updated_count = 0
        
        for key, value in params.items():
            cursor.execute("""
                INSERT OR REPLACE INTO aeon_system_parameters 
                (parameter_key, parameter_value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), int(time.time())))
            updated_count += 1
        
        self.logger.info(f"✓ Updated {updated_count} system parameter(s)")
        
        # Log parameter change
        cursor.execute("""
            INSERT INTO aeon_consensus_log 
            (timestamp, event_type, proposal_hash, details)
            VALUES (?, 'PARAMETER_CHANGE', ?, ?)
        """, (
            int(time.time()),
            proposal_hash,
            json.dumps({"parameters_updated": list(params.keys())})
        ))
    
    def _log_high_priority_action(self, conn: sqlite3.Connection, proposal_hash: str, 
                                  action_type: str, content: Dict):
        """Log high-priority actions (security updates, emergency actions)"""
        self.logger.warning(f"⚠️  HIGH PRIORITY: {action_type} proposal accepted")
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO aeon_consensus_log 
            (timestamp, event_type, proposal_hash, details)
            VALUES (?, ?, ?, ?)
        """, (
            int(time.time()),
            action_type,
            proposal_hash,
            json.dumps(content)
        ))
    
    def run_evaluation_cycle(self) -> Tuple[int, int]:
        """
        Run one complete evaluation cycle
        
        Returns:
            Tuple of (proposals_evaluated, successes)
        """
        self.logger.info("Starting consensus evaluation cycle")
        
        expired_proposals = self.get_expired_proposals()
        
        if not expired_proposals:
            self.logger.info("No expired proposals to evaluate")
            return 0, 0
        
        self.logger.info(f"Found {len(expired_proposals)} expired proposal(s)")
        
        successes = 0
        for proposal in expired_proposals:
            try:
                # Calculate vote results
                vote_result = self.calculate_vote_results(proposal['proposal_hash'])
                
                if not vote_result:
                    self.logger.warning(f"Could not calculate votes for {proposal['proposal_hash'][:16]}...")
                    continue
                
                # Execute decision
                success = self.execute_proposal_decision(proposal, vote_result)
                
                if success:
                    successes += 1
                    
            except Exception as e:
                self.logger.error(f"Error evaluating proposal {proposal['proposal_hash'][:16]}...: {e}")
        
        self.logger.info(f"Evaluation cycle completed: {successes}/{len(expired_proposals)} successful")
        return len(expired_proposals), successes
    
    def run_cleanup(self):
        """Cleanup old data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Archive old proposals (older than configured days)
            archive_threshold = int(time.time()) - (ConsensusConfig.ARCHIVE_AFTER_DAYS * 24 * 3600)
            
            cursor.execute("""
                UPDATE aeon_collective_proposals 
                SET status = 'ARCHIVED'
                WHERE status IN ('ACCEPTED', 'REJECTED')
                AND created_at < ?
            """, (archive_threshold,))
            
            archived = cursor.rowcount
            if archived > 0:
                self.logger.info(f"✓ Archived {archived} old proposal(s)")
            
            conn.commit()
    
    def get_statistics(self) -> Dict:
        """Get consensus engine statistics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            stats = {}
            
            # Proposal stats
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM aeon_collective_proposals 
                GROUP BY status
            """)
            stats['proposals_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # Node stats
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM aeon_nodes 
                GROUP BY status
            """)
            stats['nodes_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # Recent decisions
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM aeon_consensus_log 
                WHERE event_type = 'PROPOSAL_DECIDED'
                AND timestamp > ?
            """, (int(time.time()) - 86400,))  # Last 24 hours
            result = cursor.fetchone()
            stats['decisions_last_24h'] = result['count'] if result else 0
            
            return stats

# =============================================================================
# SCHEDULER
# =============================================================================

class ConsensusScheduler:
    """Scheduler for running consensus engine periodically"""
    
    def __init__(self, engine: ConsensusEngine):
        self.engine = engine
        self.running = False
    
    def run_scheduled_check(self):
        """Run the evaluation cycle"""
        try:
            proposals_evaluated, successes = self.engine.run_evaluation_cycle()
            
            if proposals_evaluated > 0:
                self.engine.logger.info(
                    f"Scheduled check completed: "
                    f"{successes}/{proposals_evaluated} proposal(s) processed"
                )
                
        except Exception as e:
            self.engine.logger.error(f"Scheduled check failed: {e}")
            import traceback
            traceback.print_exc()
    
    def run_cleanup_check(self):
        """Run cleanup task"""
        try:
            self.engine.run_cleanup()
        except Exception as e:
            self.engine.logger.error(f"Cleanup failed: {e}")
    
    def start(self):
        """Start the scheduler"""
        self.running = True
        self.engine.logger.info("✓ Consensus scheduler started")
        
        # Schedule evaluation every minute
        schedule.every(ConsensusConfig.CHECK_INTERVAL_MINUTES).minutes.do(
            self.run_scheduled_check
        )
        
        # Schedule cleanup daily
        schedule.every(ConsensusConfig.CLEANUP_INTERVAL_HOURS).hours.do(
            self.run_cleanup_check
        )
        
        # Run immediately on startup
        self.run_scheduled_check()
        
        # Keep running
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds
                
        except KeyboardInterrupt:
            self.engine.logger.info("Consensus scheduler stopped by user")
        except Exception as e:
            self.engine.logger.error(f"Scheduler error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        self.engine.logger.info("Consensus scheduler stopped")

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='AEON NEXUS Consensus Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run once and exit
  python consensus_engine.py --once
  
  # Run as daemon
  python consensus_engine.py
  
  # Setup database only
  python consensus_engine.py --setup
  
  # Custom database path
  python consensus_engine.py --db-path /path/to/aeon.db
  
  # Verbose logging
  python consensus_engine.py --verbose
        """
    )
    
    parser.add_argument('--db-path', 
                       help='Database path', 
                       default=ConsensusConfig.DB_PATH)
    parser.add_argument('--quorum', 
                       type=float, 
                       help='Quorum percentage (0.0-1.0)', 
                       default=ConsensusConfig.QUORUM_PERCENTAGE)
    parser.add_argument('--once', 
                       action='store_true', 
                       help='Run once and exit')
    parser.add_argument('--setup', 
                       action='store_true', 
                       help='Setup database schema only')
    parser.add_argument('--verbose', 
                       action='store_true', 
                       help='Verbose logging')
    parser.add_argument('--stats', 
                       action='store_true', 
                       help='Show statistics and exit')
    
    args = parser.parse_args()
    
    # Setup logging level
    if args.verbose:
        ConsensusConfig.LOG_LEVEL = logging.DEBUG
    
    # Create engine
    try:
        engine = ConsensusEngine(db_path=args.db_path, quorum=args.quorum)
    except Exception as e:
        print(f"ERROR: Failed to initialize consensus engine: {e}")
        return 1
    
    if args.setup:
        print("✓ Database schema setup completed")
        return 0
    
    if args.stats:
        stats = engine.get_statistics()
        print("\n=== CONSENSUS ENGINE STATISTICS ===\n")
        print("Proposals by status:")
        for status, count in stats.get('proposals_by_status', {}).items():
            print(f"  {status}: {count}")
        print("\nNodes by status:")
        for status, count in stats.get('nodes_by_status', {}).items():
            print(f"  {status}: {count}")
        print(f"\nDecisions in last 24h: {stats.get('decisions_last_24h', 0)}")
        return 0
    
    if args.once:
        # Run single evaluation cycle
        print("Running single evaluation cycle...")
        proposals_evaluated, successes = engine.run_evaluation_cycle()
        print(f"✓ Evaluation complete: {successes}/{proposals_evaluated} proposal(s) processed")
        engine.run_cleanup()
        print("✓ Cleanup complete")
        return 0
    else:
        # Run as daemon with scheduler
        scheduler = ConsensusScheduler(engine)
        
        try:
            scheduler.start()
        except KeyboardInterrupt:
            print("\n\n✓ Consensus engine stopped")
            return 0
        except Exception as e:
            print(f"\nERROR: {e}")
            return 1

if __name__ == "__main__":
    sys.exit(main())
