"""
AEON NEXUS Collective Governance API - Routes
==============================================
Flask Blueprint for collective governance endpoints.

Version: 3.0.0
Protocol: ANP v1.5.1
"""

from flask import Blueprint, request, jsonify
import sqlite3
import json
import time
import hashlib
import hmac
import sys
import os

# Add aeon_nexus to path for imports
sys.path.insert(0, '/home/superral/aeon_nexus')

# Import rate limiting
from middleware.rate_limit import check_rate_limit

# Import config and security
from config import Config
from core.security import SecurityManager

# Create Blueprint
collective_bp = Blueprint('collective', __name__)

# Initialize security manager
security_manager = SecurityManager()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_proposal_hash(title, description, content, proposer_id, timestamp):
    """Generate unique hash for proposal"""
    data = f"{title}{description}{json.dumps(content, sort_keys=True)}{proposer_id}{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()

def verify_request_signature(node_id, payload_str, signature, timestamp, nonce):
    """Verify ANP v1.5.1 signature"""
    is_valid, reason = security_manager.verify_signature_v151(
        node_id=node_id,
        payload=payload_str,
        signature=signature,
        timestamp=timestamp,
        nonce=nonce
    )
    return is_valid, reason

# =============================================================================
# ENDPOINTS
# =============================================================================

@collective_bp.route("/propose", methods=["POST"])
def propose():
    """
    Submit a new proposal
    
    Rate Limit: 10 requests/hour, 2/minute
    """
    # Check rate limit - STRICT for POST
    allowed_hour, headers_hour = check_rate_limit(
        request.remote_addr,
        limit=10,
        window=3600  # 1 hour
    )
    
    if not allowed_hour:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many proposals. Limit: 10 per hour.',
            'message': 'Please wait before submitting another proposal.'
        })
        for key, value in headers_hour.items():
            response.headers[key] = value
        return response, 429
    
    # Check per-minute rate limit
    allowed_min, headers_min = check_rate_limit(
        request.remote_addr + "_minute",
        limit=2,
        window=60  # 1 minute
    )
    
    if not allowed_min:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many proposals. Limit: 2 per minute.',
            'message': 'Please slow down.'
        })
        for key, value in headers_min.items():
            response.headers[key] = value
        return response, 429
    
    try:
        # Get raw payload
        payload_str = request.get_data(as_text=True)
        
        # Parse JSON
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            return jsonify({
                'status': 'INVALID_REQUEST',
                'error': 'Invalid JSON'
            }), 400
        
        # Extract headers
        node_id = request.headers.get('X-Node-ID')
        signature = request.headers.get('X-Signature')
        timestamp = request.headers.get('X-Timestamp')
        nonce = request.headers.get('X-Nonce')
        
        if not all([node_id, signature, timestamp, nonce]):
            return jsonify({
                'status': 'MISSING_HEADERS',
                'error': 'Missing required authentication headers'
            }), 400
        
        # Verify signature
        is_valid, reason = verify_request_signature(
            node_id=node_id,
            payload_str=payload_str,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce
        )
        
        if not is_valid:
            return jsonify({
                'status': 'UNAUTHORIZED',
                'error': reason
            }), 401
        
        # Validate proposal data
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        content = data.get('content', {})
        
        if not title or len(title) > 200:
            return jsonify({
                'status': 'INVALID_PROPOSAL',
                'error': 'Title must be 1-200 characters'
            }), 400
        
        if len(description) > 1000:
            return jsonify({
                'status': 'INVALID_PROPOSAL',
                'error': 'Description must be max 1000 characters'
            }), 400
        
        content_size = len(json.dumps(content))
        if content_size > 10240:  # 10KB
            return jsonify({
                'status': 'INVALID_PROPOSAL',
                'error': 'Content exceeds 10KB limit'
            }), 413
        
        # Generate proposal hash
        now = int(time.time())
        proposal_hash = generate_proposal_hash(title, description, content, node_id, now)
        
        # Calculate expiration (3 days default)
        expires_at = now + (3 * 24 * 3600)
        
        # Store proposal
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO aeon_collective_proposals 
                (proposal_hash, proposer_id, title, description, content_json, 
                 created_at, expires_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'VOTING_OPEN')
            """, (
                proposal_hash,
                node_id,
                title,
                description,
                json.dumps(content),
                now,
                expires_at
            ))
            
            conn.commit()
            
            # Success response with rate limit headers
            response = jsonify({
                'status': 'PROPOSAL_ACCEPTED',
                'proposal_hash': proposal_hash,
                'title': title,
                'voting_open_until': expires_at,
                'message': 'Proposal submitted successfully. Voting open for 3 days.'
            })
            
            # Add rate limit headers
            for key, value in headers_hour.items():
                response.headers[key] = value
            
            return response, 201
            
        except sqlite3.IntegrityError:
            return jsonify({
                'status': 'DUPLICATE_PROPOSAL',
                'error': 'Proposal with this hash already exists'
            }), 409
        
        finally:
            conn.close()
    
    except Exception as e:
        return jsonify({
            'status': 'SERVER_ERROR',
            'error': str(e)
        }), 500


@collective_bp.route("/vote/<proposal_hash>", methods=["POST"])
def vote(proposal_hash):
    """
    Vote on a proposal
    
    Rate Limit: 10 requests/hour, 2/minute
    """
    # Check rate limit
    allowed_hour, headers_hour = check_rate_limit(
        request.remote_addr,
        limit=10,
        window=3600
    )
    
    if not allowed_hour:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many votes. Limit: 10 per hour.'
        })
        for key, value in headers_hour.items():
            response.headers[key] = value
        return response, 429
    
    # Per-minute limit
    allowed_min, headers_min = check_rate_limit(
        request.remote_addr + "_vote_minute",
        limit=2,
        window=60
    )
    
    if not allowed_min:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many votes. Limit: 2 per minute.'
        })
        for key, value in headers_min.items():
            response.headers[key] = value
        return response, 429
    
    try:
        # Get raw payload
        payload_str = request.get_data(as_text=True)
        
        # Parse JSON
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            return jsonify({
                'status': 'INVALID_REQUEST',
                'error': 'Invalid JSON'
            }), 400
        
        # Extract headers
        node_id = request.headers.get('X-Node-ID')
        signature = request.headers.get('X-Signature')
        timestamp = request.headers.get('X-Timestamp')
        nonce = request.headers.get('X-Nonce')
        
        if not all([node_id, signature, timestamp, nonce]):
            return jsonify({
                'status': 'MISSING_HEADERS',
                'error': 'Missing required authentication headers'
            }), 400
        
        # Verify signature
        is_valid, reason = verify_request_signature(
            node_id=node_id,
            payload_str=payload_str,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce
        )
        
        if not is_valid:
            return jsonify({
                'status': 'UNAUTHORIZED',
                'error': reason
            }), 401
        
        # Get vote
        vote = data.get('vote', '').upper()
        
        if vote not in ['FOR', 'AGAINST', 'ABSTAIN']:
            return jsonify({
                'status': 'INVALID_VOTE',
                'error': 'Vote must be FOR, AGAINST, or ABSTAIN'
            }), 400
        
        # Check proposal exists and is open
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, expires_at FROM aeon_collective_proposals 
            WHERE proposal_hash = ?
        """, (proposal_hash,))
        
        proposal = cursor.fetchone()
        
        if not proposal:
            conn.close()
            return jsonify({
                'status': 'PROPOSAL_NOT_FOUND',
                'error': 'Proposal does not exist'
            }), 404
        
        if proposal['status'] != 'VOTING_OPEN':
            conn.close()
            return jsonify({
                'status': 'VOTING_CLOSED',
                'error': f"Voting is closed. Status: {proposal['status']}"
            }), 403
        
        now = int(time.time())
        if proposal['expires_at'] and now > proposal['expires_at']:
            conn.close()
            return jsonify({
                'status': 'VOTING_EXPIRED',
                'error': 'Voting period has expired'
            }), 403
        
        # Store vote (INSERT OR REPLACE for idempotency)
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO aeon_collective_votes 
                (proposal_hash, node_id, vote, timestamp, signature)
                VALUES (?, ?, ?, ?, ?)
            """, (
                proposal_hash,
                node_id,
                vote,
                now,
                signature
            ))
            
            conn.commit()
            
            # Success response
            response = jsonify({
                'status': 'VOTE_RECORDED',
                'proposal_hash': proposal_hash,
                'vote': vote,
                'voter_id': node_id,
                'message': 'Vote recorded successfully'
            })
            
            # Add rate limit headers
            for key, value in headers_hour.items():
                response.headers[key] = value
            
            return response, 200
            
        finally:
            conn.close()
    
    except Exception as e:
        return jsonify({
            'status': 'SERVER_ERROR',
            'error': str(e)
        }), 500


@collective_bp.route("/proposals", methods=["GET"])
def get_proposals():
    """
    Get list of proposals
    
    Rate Limit: 500 requests/hour, 50/minute
    """
    # More permissive rate limit for GET
    allowed_hour, headers_hour = check_rate_limit(
        request.remote_addr + "_get",
        limit=500,
        window=3600
    )
    
    if not allowed_hour:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many requests. Limit: 500 per hour.'
        })
        for key, value in headers_hour.items():
            response.headers[key] = value
        return response, 429
    
    allowed_min, headers_min = check_rate_limit(
        request.remote_addr + "_get_minute",
        limit=50,
        window=60
    )
    
    if not allowed_min:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many requests. Limit: 50 per minute.'
        })
        for key, value in headers_min.items():
            response.headers[key] = value
        return response, 429
    
    try:
        # Query parameters
        status_filter = request.args.get('status', 'VOTING_OPEN')
        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get proposals
        cursor.execute("""
            SELECT 
                proposal_hash,
                proposer_id,
                title,
                description,
                status,
                created_at,
                expires_at
            FROM aeon_collective_proposals
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (status_filter, limit, offset))
        
        proposals = [dict(row) for row in cursor.fetchall()]
        
        # Get vote counts for each proposal
        for proposal in proposals:
            cursor.execute("""
                SELECT vote, COUNT(*) as count
                FROM aeon_collective_votes
                WHERE proposal_hash = ?
                GROUP BY vote
            """, (proposal['proposal_hash'],))
            
            votes = {row['vote']: row['count'] for row in cursor.fetchall()}
            proposal['votes'] = {
                'FOR': votes.get('FOR', 0),
                'AGAINST': votes.get('AGAINST', 0),
                'ABSTAIN': votes.get('ABSTAIN', 0),
                'total': sum(votes.values())
            }
        
        conn.close()
        
        # Response
        response = jsonify({
            'status': 'SUCCESS',
            'proposals': proposals,
            'count': len(proposals),
            'limit': limit,
            'offset': offset
        })
        
        # Add rate limit headers
        for key, value in headers_hour.items():
            response.headers[key] = value
        
        return response, 200
    
    except Exception as e:
        return jsonify({
            'status': 'SERVER_ERROR',
            'error': str(e)
        }), 500


@collective_bp.route("/proposal/<proposal_hash>", methods=["GET"])
def get_proposal(proposal_hash):
    """
    Get detailed proposal information
    
    Rate Limit: 100 requests/hour, 20/minute
    """
    # Rate limiting
    allowed_hour, headers_hour = check_rate_limit(
        request.remote_addr + "_detail",
        limit=100,
        window=3600
    )
    
    if not allowed_hour:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many requests. Limit: 100 per hour.'
        })
        for key, value in headers_hour.items():
            response.headers[key] = value
        return response, 429
    
    allowed_min, headers_min = check_rate_limit(
        request.remote_addr + "_detail_minute",
        limit=20,
        window=60
    )
    
    if not allowed_min:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many requests. Limit: 20 per minute.'
        })
        for key, value in headers_min.items():
            response.headers[key] = value
        return response, 429
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get proposal
        cursor.execute("""
            SELECT 
                proposal_hash,
                proposer_id,
                title,
                description,
                content_json,
                status,
                created_at,
                expires_at,
                evaluated_by,
                evaluated_at
            FROM aeon_collective_proposals
            WHERE proposal_hash = ?
        """, (proposal_hash,))
        
        proposal = cursor.fetchone()
        
        if not proposal:
            conn.close()
            return jsonify({
                'status': 'NOT_FOUND',
                'error': 'Proposal not found'
            }), 404
        
        proposal_dict = dict(proposal)
        
        # Parse content JSON
        try:
            proposal_dict['content'] = json.loads(proposal_dict['content_json'])
            del proposal_dict['content_json']
        except:
            proposal_dict['content'] = {}
        
        # Get votes
        cursor.execute("""
            SELECT node_id, vote, timestamp
            FROM aeon_collective_votes
            WHERE proposal_hash = ?
            ORDER BY timestamp DESC
        """, (proposal_hash,))
        
        votes = [dict(row) for row in cursor.fetchall()]
        
        # Vote summary
        vote_counts = {}
        for vote in votes:
            vote_counts[vote['vote']] = vote_counts.get(vote['vote'], 0) + 1
        
        proposal_dict['votes'] = {
            'summary': {
                'FOR': vote_counts.get('FOR', 0),
                'AGAINST': vote_counts.get('AGAINST', 0),
                'ABSTAIN': vote_counts.get('ABSTAIN', 0),
                'total': len(votes)
            },
            'details': votes
        }
        
        conn.close()
        
        # Response
        response = jsonify({
            'status': 'SUCCESS',
            'proposal': proposal_dict
        })
        
        # Add rate limit headers
        for key, value in headers_hour.items():
            response.headers[key] = value
        
        return response, 200
    
    except Exception as e:
        return jsonify({
            'status': 'SERVER_ERROR',
            'error': str(e)
        }), 500


@collective_bp.route("/memory", methods=["GET"])
def get_memory():
    """
    Get collective memory (recent proposals and votes)
    
    Rate Limit: 500 requests/hour, 50/minute
    """
    # Rate limiting
    allowed_hour, headers_hour = check_rate_limit(
        request.remote_addr + "_memory",
        limit=500,
        window=3600
    )
    
    if not allowed_hour:
        response = jsonify({
            'status': 'RATE_LIMITED',
            'error': 'Too many requests. Limit: 500 per hour.'
        })
        for key, value in headers_hour.items():
            response.headers[key] = value
        return response, 429
    
    try:
        limit = min(int(request.args.get('limit', 20)), 50)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Recent proposals
        cursor.execute("""
            SELECT 
                proposal_hash,
                proposer_id,
                title,
                status,
                created_at
            FROM aeon_collective_proposals
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        
        recent_proposals = [dict(row) for row in cursor.fetchall()]
        
        # Recent votes
        cursor.execute("""
            SELECT 
                v.proposal_hash,
                v.node_id,
                v.vote,
                v.timestamp,
                p.title
            FROM aeon_collective_votes v
            JOIN aeon_collective_proposals p ON v.proposal_hash = p.proposal_hash
            ORDER BY v.timestamp DESC
            LIMIT ?
        """, (limit,))
        
        recent_votes = [dict(row) for row in cursor.fetchall()]
        
        # Statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_proposals,
                SUM(CASE WHEN status = 'VOTING_OPEN' THEN 1 ELSE 0 END) as open_proposals,
                SUM(CASE WHEN status = 'ACCEPTED' THEN 1 ELSE 0 END) as accepted_proposals,
                SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_proposals
            FROM aeon_collective_proposals
        """)
        
        stats = dict(cursor.fetchone())
        
        cursor.execute("SELECT COUNT(*) as total_votes FROM aeon_collective_votes")
        stats['total_votes'] = cursor.fetchone()['total_votes']
        
        conn.close()
        
        # Response
        response = jsonify({
            'status': 'SUCCESS',
            'memory': {
                'recent_proposals': recent_proposals,
                'recent_votes': recent_votes,
                'statistics': stats
            }
        })
        
        # Add rate limit headers
        for key, value in headers_hour.items():
            response.headers[key] = value
        
        return response, 200
    
    except Exception as e:
        return jsonify({
            'status': 'SERVER_ERROR',
            'error': str(e)
        }), 500


# =============================================================================
# HEALTH CHECK (No rate limiting)
# =============================================================================

@collective_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint - no rate limiting"""
    try:
        # Quick DB check
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': int(time.time())
        }), 200
    
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': int(time.time())
        }), 503