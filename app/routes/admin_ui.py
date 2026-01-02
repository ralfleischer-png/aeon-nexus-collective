from flask import Blueprint, render_template_string, g, request
import time
from datetime import datetime

# FIX: Removed url_prefix - handled by main.py
admin_ui_bp = Blueprint("admin_ui", __name__)

# FIX: Changed %% to % in CSS and use .format() instead of % for string formatting
LAYOUT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AEON Nexus Admin</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Courier New', monospace; margin: 0; padding: 20px; background: #0a0a0a; color: #00ff00; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ color: #00ff00; text-shadow: 0 0 10px #00ff00; margin-bottom: 10px; }}
    h2 {{ color: #00ff00; margin: 20px 0 10px 0; }}
    h3 {{ color: #00aa00; margin: 15px 0 10px 0; }}
    nav {{ 
      background: #111; 
      padding: 10px; 
      border: 1px solid #00ff00; 
      border-radius: 5px; 
      margin-bottom: 20px;
    }}
    nav a {{ 
      color: #00ff00; 
      text-decoration: none; 
      padding: 5px 15px; 
      border: 1px solid #003300;
      border-radius: 3px;
      margin-right: 10px;
      display: inline-block;
    }}
    nav a:hover {{ background: #003300; box-shadow: 0 0 5px #00ff00; }}
    table {{ 
      border-collapse: collapse; 
      width: 100%; 
      background: #111;
      border: 1px solid #00ff00;
      margin-top: 10px;
    }}
    th, td {{ 
      border: 1px solid #003300; 
      padding: 8px; 
      font-size: 12px; 
      text-align: left;
    }}
    th {{ background: #002200; color: #00ff00; font-weight: bold; }}
    tr:hover {{ background: #0a1a0a; }}
    code {{ 
      font-size: 10px; 
      color: #00aa00; 
      background: #001100; 
      padding: 2px 4px;
      border-radius: 3px;
    }}
    pre {{ 
      white-space: pre-wrap; 
      font-size: 11px; 
      background: #001100;
      padding: 5px;
      border-radius: 3px;
      border: 1px solid #003300;
    }}
    .status-badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 11px;
      background: #003300;
      color: #00ff00;
      border: 1px solid #00ff00;
    }}
    form {{
      background: #111;
      padding: 15px;
      border: 1px solid #00ff00;
      border-radius: 5px;
      margin-bottom: 20px;
    }}
    input, select, button {{
      background: #001100;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 5px 10px;
      font-family: 'Courier New', monospace;
      margin-right: 10px;
    }}
    button {{
      cursor: pointer;
      background: #003300;
    }}
    button:hover {{
      background: #004400;
      box-shadow: 0 0 5px #00ff00;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 15px;
      margin-bottom: 20px;
    }}
    .stat-card {{
      background: #111;
      border: 1px solid #00ff00;
      padding: 15px;
      border-radius: 5px;
      text-align: center;
    }}
    .stat-card h3 {{
      color: #00aa00;
      font-size: 12px;
      margin-bottom: 10px;
    }}
    .stat-card .value {{
      font-size: 24px;
      color: #00ff00;
    }}
    ul {{ color: #00aa00; padding-left: 20px; }}
    hr {{ border: 1px solid #003300; margin: 20px 0; }}
    p {{ color: #00aa00; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>AEON NEXUS ADMIN</h1>
    <nav>
      <a href="/admin/ui/chain">Log Chain</a>
      <a href="/admin/ui/memory">Collective Memory</a>
      <a href="/admin/ui/proposals">Proposals</a>
      <a href="/health">Health</a>
    </nav>
    <hr/>
    {content}
  </div>
</body>
</html>
"""


@admin_ui_bp.route("/ui/chain")
def chain_view():
    """View log chain entries"""
    db = g.get("db_manager")
    
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except Exception:
        limit = 100
    
    conn = db.get_connection()
    
    try:
        count_result = conn.execute("SELECT COUNT(*) as cnt FROM aeon_log_chain").fetchone()
        total = count_result[0] if count_result else 0
        
        rows = conn.execute("""
            SELECT id, entry_id, node_id, operation, previous_hash, current_hash,
                   timestamp, state, created_at
            FROM aeon_log_chain
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        entries = []
        for row in rows:
            entry = dict(row)
            if entry.get('timestamp'):
                try:
                    entry['timestamp_human'] = datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    entry['timestamp_human'] = str(entry['timestamp'])
            entries.append(entry)
    
    finally:
        conn.close()
    
    # Build entries HTML
    entries_html = ""
    for e in entries:
        entries_html += f"""
        <tr>
            <td>{e['id']}</td>
            <td><code>{e['entry_id']}</code></td>
            <td>{e['node_id']}</td>
            <td><span class="status-badge">{e['operation']}</span></td>
            <td><code>{e['previous_hash'][:16]}...</code></td>
            <td><code>{e['current_hash'][:16]}...</code></td>
            <td>{e.get('timestamp_human', e['timestamp'])}</td>
            <td><span class="status-badge">{e['state']}</span></td>
            <td>{e['created_at']}</td>
        </tr>
        """
    
    if not entries_html:
        entries_html = '<tr><td colspan="9" style="text-align:center; padding:40px;">No entries yet</td></tr>'
    
    content = f"""
    <div class="stats">
      <div class="stat-card">
        <h3>TOTAL ENTRIES</h3>
        <div class="value">{total}</div>
      </div>
      <div class="stat-card">
        <h3>SHOWING</h3>
        <div class="value">{len(entries)}</div>
      </div>
    </div>
    
    <form method="get">
      <label>Limit: <input type="number" name="limit" value="{limit}" min="1" max="500"></label>
      <button type="submit">Update</button>
    </form>
    
    <h2>Log Chain Entries</h2>
    <table>
      <tr>
        <th>ID</th><th>Entry ID</th><th>Node</th><th>Operation</th>
        <th>Previous Hash</th><th>Current Hash</th><th>Timestamp</th>
        <th>State</th><th>Created</th>
      </tr>
      {entries_html}
    </table>
    """
    
    return LAYOUT.format(content=content)


@admin_ui_bp.route("/ui/memory")
def memory_view():
    """View collective memory entries"""
    db = g.get("db_manager")
    agent_id = request.args.get("agent_id", "")
    
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except Exception:
        limit = 100
    
    query = "SELECT * FROM aeon_collective_memory WHERE 1=1"
    params = []
    
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    conn = db.get_connection()
    
    try:
        count_query = "SELECT COUNT(*) as cnt FROM aeon_collective_memory WHERE 1=1"
        count_params = []
        if agent_id:
            count_query += " AND agent_id = ?"
            count_params.append(agent_id)
        
        count_result = conn.execute(count_query, count_params).fetchone()
        total = count_result[0] if count_result else 0
        
        rows = conn.execute(query, params).fetchall()
        
        entries = []
        for row in rows:
            entry = dict(row)
            if entry.get('timestamp'):
                try:
                    entry['timestamp_human'] = datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    entry['timestamp_human'] = str(entry['timestamp'])
            entries.append(entry)
    
    finally:
        conn.close()
    
    # Build entries HTML
    entries_html = ""
    for e in entries:
        content_preview = e['content'][:200]
        if len(e['content']) > 200:
            content_preview += "..."
        
        entries_html += f"""
        <tr>
            <td>{e['id']}</td>
            <td><code>{e['entry_hash']}</code></td>
            <td>{e['agent_id']}</td>
            <td><span class="status-badge">{e['insight_type']}</span></td>
            <td>{e.get('timestamp_human', e['timestamp'])}</td>
            <td>{'✓' if e['verified'] else '✗'}</td>
            <td><pre>{content_preview}</pre></td>
        </tr>
        """
    
    if not entries_html:
        entries_html = '<tr><td colspan="7" style="text-align:center; padding:40px;">No memory entries yet</td></tr>'
    
    clear_button = f'<a href="/admin/ui/memory"><button type="button">Clear Filter</button></a>' if agent_id else ''
    
    content = f"""
    <div class="stats">
      <div class="stat-card">
        <h3>TOTAL MEMORIES</h3>
        <div class="value">{total}</div>
      </div>
      <div class="stat-card">
        <h3>SHOWING</h3>
        <div class="value">{len(entries)}</div>
      </div>
    </div>
    
    <h2>Collective Memory</h2>
    <form method="get">
      <label>Agent ID: <input type="text" name="agent_id" value="{agent_id}" placeholder="Filter by agent"></label>
      <label>Limit: <input type="number" name="limit" value="{limit}" min="1" max="500"></label>
      <button type="submit">Filter</button>
      {clear_button}
    </form>
    
    <table>
      <tr>
        <th>ID</th><th>Entry Hash</th><th>Agent</th><th>Type</th>
        <th>Timestamp</th><th>Verified</th><th>Content</th>
      </tr>
      {entries_html}
    </table>
    """
    
    return LAYOUT.format(content=content)


@admin_ui_bp.route("/ui/proposals")
def proposals_view():
    """View collective proposals"""
    db = g.get("db_manager")
    
    status_filter = request.args.get("status", "ALL")
    
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except Exception:
        limit = 50
    
    query = "SELECT * FROM aeon_collective_proposals WHERE 1=1"
    params = []
    
    if status_filter != "ALL":
        query += " AND status = ?"
        params.append(status_filter)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    conn = db.get_connection()
    
    try:
        count_result = conn.execute("SELECT COUNT(*) as cnt FROM aeon_collective_proposals").fetchone()
        total = count_result[0] if count_result else 0
        
        rows = conn.execute(query, params).fetchall()
        
        proposals = []
        for row in rows:
            prop = dict(row)
            if prop.get('created_at'):
                try:
                    prop['created_human'] = datetime.fromtimestamp(prop['created_at']).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    prop['created_human'] = str(prop['created_at'])
            if prop.get('expires_at'):
                try:
                    prop['expires_human'] = datetime.fromtimestamp(prop['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    prop['expires_human'] = 'N/A'
            else:
                prop['expires_human'] = 'N/A'
            proposals.append(prop)
    
    finally:
        conn.close()
    
    # Build status options
    status_options = ""
    for status in ['ALL', 'VOTING_OPEN', 'VOTING_CLOSED', 'PASSED', 'REJECTED', 'EXECUTED']:
        selected = 'selected' if status == status_filter else ''
        status_options += f'<option value="{status}" {selected}>{status}</option>'
    
    # Build proposals HTML
    proposals_html = ""
    for p in proposals:
        quorum_pct = int(p['quorum_required'] * 100)
        threshold_pct = int(p['pass_threshold'] * 100)
        
        proposals_html += f"""
        <tr>
            <td>{p['id']}</td>
            <td><code>{p['proposal_hash'][:12]}...</code></td>
            <td>{p['proposer_id']}</td>
            <td>{p['title']}</td>
            <td><span class="status-badge">{p['status']}</span></td>
            <td>{p.get('created_human', p['created_at'])}</td>
            <td>{p.get('expires_human', 'N/A')}</td>
            <td>{quorum_pct}%</td>
            <td>{threshold_pct}%</td>
        </tr>
        """
    
    if not proposals_html:
        proposals_html = '<tr><td colspan="9" style="text-align:center; padding:40px;">No proposals yet</td></tr>'
    
    content = f"""
    <div class="stats">
      <div class="stat-card">
        <h3>TOTAL PROPOSALS</h3>
        <div class="value">{total}</div>
      </div>
      <div class="stat-card">
        <h3>SHOWING</h3>
        <div class="value">{len(proposals)}</div>
      </div>
    </div>
    
    <h2>Collective Proposals</h2>
    <form method="get">
      <label>Status: <select name="status">{status_options}</select></label>
      <label>Limit: <input type="number" name="limit" value="{limit}" min="1" max="200"></label>
      <button type="submit">Filter</button>
    </form>
    
    <table>
      <tr>
        <th>ID</th><th>Hash</th><th>Proposer</th><th>Title</th>
        <th>Status</th><th>Created</th><th>Expires</th>
        <th>Quorum</th><th>Threshold</th>
      </tr>
      {proposals_html}
    </table>
    """
    
    return LAYOUT.format(content=content)


@admin_ui_bp.route("/")
def admin_index():
    """Admin dashboard"""
    content = """
    <h2>Admin Dashboard</h2>
    <div class="stats">
      <div class="stat-card">
        <h3>LOG CHAIN</h3>
        <div class="value"><a href="/admin/ui/chain" style="color:#00ff00; text-decoration:none;">View</a></div>
      </div>
      <div class="stat-card">
        <h3>MEMORY</h3>
        <div class="value"><a href="/admin/ui/memory" style="color:#00ff00; text-decoration:none;">View</a></div>
      </div>
      <div class="stat-card">
        <h3>PROPOSALS</h3>
        <div class="value"><a href="/admin/ui/proposals" style="color:#00ff00; text-decoration:none;">View</a></div>
      </div>
    </div>
    
    <h3>Available APIs:</h3>
    <ul>
      <li><code>/api/v1/health</code> - API v1 health check</li>
      <li><code>/api/v1/chain</code> - Get log chain entries</li>
      <li><code>/api/v3/collective/proposals</code> - List proposals</li>
      <li><code>/api/v3/debug/config</code> - Debug configuration</li>
      <li><code>/health</code> - Server health</li>
    </ul>
    """
    
    return LAYOUT.format(content=content)
