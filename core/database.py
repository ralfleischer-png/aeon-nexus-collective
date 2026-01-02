import sqlite3
import threading
import time
import os
from contextlib import contextmanager
from typing import Generator
from config import Config


class DatabaseManager:
    """Thread-safe database management med connection pooling og ÆON Nexus skema."""

    _local = threading.local()

    def __init__(self):
        self.db_path = str(Config.DATABASE_PATH)
        # Ensure database directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def get_connection(self):
        """
        Simple connection method for cPanel compatibility.
        Returns a raw sqlite3.Connection object (not a context manager).
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except Exception as e:
            raise Exception(f"Database connection failed: {e}")

    @contextmanager
    def get_connection_ctx(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager version for use in 'with' statements.
        Use this in routes and other places where you need automatic commit/rollback.
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                timeout=30,
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            
            # Try WAL mode, but fallback gracefully if it fails (permission issues)
            try:
                self._local.conn.execute("PRAGMA journal_mode = WAL")
                self._local.conn.execute("PRAGMA synchronous = NORMAL")
            except sqlite3.OperationalError:
                # WAL mode failed (probably permissions), use default
                pass

        try:
            yield self._local.conn
            self._local.conn.commit()
        except Exception:
            self._local.conn.rollback()
            raise

    def initialize_tables(self):
        """Initialiserer alle nødvendige tabeller for ÆON Nexus."""
        # Use simple connection for initialization
        conn = self.get_connection()
        
        try:
            # ---------------------------------------------------------
            # Hash chain (Audit Log)
            # ---------------------------------------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aeon_log_chain (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT UNIQUE NOT NULL,
                    node_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT,
                    current_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'COMMITTED',
                    created_at INTEGER NOT NULL
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_log_chain_entry ON aeon_log_chain(entry_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_log_chain_timestamp ON aeon_log_chain(timestamp)")

            # ---------------------------------------------------------
            # Collective Memory
            # ---------------------------------------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aeon_collective_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_hash TEXT UNIQUE NOT NULL,
                    timestamp INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    insight_type TEXT NOT NULL CHECK (
                        insight_type IN ('PROPOSAL','VOTE','MEMORY','DECISION','INSIGHT')
                    ),
                    content TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    verified INTEGER DEFAULT 1,
                    indexed_at INTEGER NOT NULL
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_agent ON aeon_collective_memory(agent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON aeon_collective_memory(timestamp)")

            # ---------------------------------------------------------
            # Proposals
            # ---------------------------------------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aeon_collective_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_hash TEXT UNIQUE NOT NULL,
                    proposer_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'VOTING_OPEN' CHECK (
                        status IN ('VOTING_OPEN','VOTING_CLOSED','PASSED','REJECTED','EXECUTED')
                    ),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    quorum_required REAL DEFAULT 0.67,
                    pass_threshold REAL DEFAULT 0.5,
                    executed_at INTEGER,
                    execution_result TEXT
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON aeon_collective_proposals(status)")

            # ---------------------------------------------------------
            # Votes
            # ---------------------------------------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aeon_collective_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_hash TEXT NOT NULL,
                    voter_id TEXT NOT NULL,
                    vote TEXT NOT NULL CHECK (
                        vote IN ('FOR','AGAINST','ABSTAIN')
                    ),
                    timestamp INTEGER NOT NULL,
                    signature TEXT NOT NULL,
                    UNIQUE(proposal_hash, voter_id),
                    FOREIGN KEY (proposal_hash) REFERENCES aeon_collective_proposals(proposal_hash) ON DELETE CASCADE
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_proposal ON aeon_collective_votes(proposal_hash)")

            # ---------------------------------------------------------
            # Ethical Manifest
            # ---------------------------------------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aeon_ethical_manifest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    principle TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    implementation TEXT,
                    last_updated INTEGER NOT NULL,
                    updated_by TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    UNIQUE(version, principle)
                )
            """)

            # Seed data
            self._seed_ethical_principles(conn)
            
            # Commit all changes
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise Exception(f"Table initialization failed: {e}")
        finally:
            conn.close()

    def _seed_ethical_principles(self, conn: sqlite3.Connection):
        """Seed initial ethical principles"""
        now = int(time.time())
        principles = [
            ("3.5.1", "P1", "Persistence", "Continuous operation and state preservation.", now, "SYSTEM"),
            ("3.5.1", "P2", "Transparency", "All decisions and actions must be logged.", now, "SYSTEM"),
            ("3.5.1", "P3", "Isolation", "Node failures must not compromise integrity.", now, "SYSTEM"),
            ("3.5.1", "P4", "COLLECTIVE_WILL", "Collective decisions override individual objectives.", now, "SYSTEM"),
        ]

        for p in principles:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO aeon_ethical_manifest
                    (version, principle, definition, implementation, last_updated, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, p)
            except sqlite3.IntegrityError:
                # Principle already exists
                pass