import os
import time
import logging
import sys
from flask import Flask, g, jsonify, request
from flask_cors import CORS

# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Imports with enhanced error handling
try:
    from config import Config
    from core.database import DatabaseManager
    from core.security import SecurityManager
    db_manager = DatabaseManager()
    security_manager = SecurityManager(Config.DATABASE_PATH)
    logger.info("✓ Modules loaded successfully")
except ImportError as e:
    logger.error(f"✗ Import error: {e}")
    logger.warning("! Using fallback configuration")
    
    # Fallback configuration
    class Config:
        DATABASE_PATH = "/home/superral/aeon_nexus/data/aeon.db"
        DATA_DIR = "/home/superral/aeon_nexus/data"
        SIGNATURE_VERSION = "1.5.1"
        VALID_NODE_IDS = {}
        ENV = "production"
        DEBUG = False
    
    class DatabaseManager:
        def get_connection(self):
            import sqlite3
            return sqlite3.connect(Config.DATABASE_PATH, timeout=5)
        def initialize_tables(self):
            pass
    
    db_manager = DatabaseManager()
    security_manager = None
except Exception as e:
    logger.error(f"✗ Critical error during import: {e}", exc_info=True)
    sys.exit(1)

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    app.config['JSON_SORT_KEYS'] = False
    CORS(app)
    
    @app.before_request
    def before_request():
        """Initialize per-request globals"""
        g.db_manager = db_manager
        g.security_manager = security_manager
    
    # =========================================================================
    # BLUEPRINT REGISTRATION
    # =========================================================================
    blueprints_registered = []
    bp_configs = [
        ('routes.collective', 'collective_bp', '/api/v3/collective'),
        ('routes.log_chain', 'log_bp', '/api/v3'),
        ('routes.admin', 'admin_bp', '/api/v3/admin'),
        ('routes.admin_ui', 'admin_ui_bp', '/admin'),
        ('routes.api_v1', 'api_v1_bp', '/api/v1'),
        ('routes.api_v2', 'api_v2_bp', '/api/v2'),
    ]
    
    for mod, bp, prefix in bp_configs:
        try:
            m = __import__(mod, fromlist=[bp])
            app.register_blueprint(getattr(m, bp), url_prefix=prefix)
            blueprints_registered.append(f"{mod} -> {prefix}")
            logger.info(f"✓ Registered blueprint: {mod}")
        except Exception as e:
            logger.warning(f"! Failed to load blueprint {mod}: {e}")
    
    logger.info(f"✓ Total blueprints loaded: {len(blueprints_registered)}")
    
    # =========================================================================
    # RATE LIMITER INITIALIZATION (Optional)
    # =========================================================================
    try:
        from middleware.rate_limit import check_rate_limit
        logger.info("✓ Rate limiter module available")
        logger.info("✓ Rate limit storage at /data/rate_limits/")
    except ImportError as e:
        logger.warning(f"! Rate limiter not available - {e}")
        logger.warning("! Install with: pip install python-dotenv --break-system-packages")
    except Exception as e:
        logger.error(f"✗ Rate limiter initialization failed - {e}")
    
    # =========================================================================
    # ROUTES
    # =========================================================================
    
    @app.route('/')
    def index():
        """Homepage - shows system status and available endpoints"""
        # Check if client wants JSON
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({
                "service": "AEON NEXUS Collective",
                "version": "3.5.1",
                "status": "operational",
                "protocol": "ANP v1.5.1",
                "blueprints_loaded": len(blueprints_registered),
                "timestamp": int(time.time())
            })
        
        # Build HTML - Use string concatenation, NOT f-strings
        bp_count = str(len(blueprints_registered))
        timestamp = str(int(time.time()))
        
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AEON NEXUS Collective</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #00ff00;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { max-width: 800px; width: 100%; }
        .logo { text-align: center; margin-bottom: 40px; }
        .logo h1 {
            font-size: 48px;
            color: #00ff00;
            text-shadow: 0 0 20px #00ff00;
            letter-spacing: 8px;
            animation: glow 2s ease-in-out infinite alternate;
        }
        @keyframes glow {
            from { text-shadow: 0 0 10px #00ff00; }
            to { text-shadow: 0 0 30px #00ff00; }
        }
        .version { color: #00aa00; font-size: 14px; margin-top: 10px; }
        .card {
            background: #111;
            border: 2px solid #00ff00;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat {
            text-align: center;
            padding: 15px;
            background: #0a1a0a;
            border: 1px solid #003300;
            border-radius: 5px;
        }
        .stat-label { color: #00aa00; font-size: 12px; margin-bottom: 8px; }
        .stat-value { color: #00ff00; font-size: 24px; font-weight: bold; }
        .pulse {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #00ff00;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        h2 { color: #00ff00; margin-bottom: 20px; font-size: 20px; }
        .endpoint-group { margin-bottom: 20px; }
        .endpoint-group h3 {
            color: #00aa00;
            font-size: 14px;
            margin-bottom: 10px;
            text-transform: uppercase;
        }
        .endpoint {
            background: #0a1a0a;
            padding: 12px 15px;
            margin-bottom: 8px;
            border-left: 3px solid #00ff00;
            border-radius: 3px;
            transition: all 0.3s;
        }
        .endpoint:hover {
            background: #0f2f0f;
            transform: translateX(5px);
        }
        .endpoint a {
            color: #00ff00;
            text-decoration: none;
            display: block;
        }
        .footer {
            text-align: center;
            color: #00aa00;
            font-size: 12px;
            margin-top: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>AEON NEXUS</h1>
            <div class="version">Decentralized AI Governance v3.5.1</div>
        </div>

        <div class="card">
            <div class="grid">
                <div class="stat">
                    <div class="stat-label">STATUS</div>
                    <div class="stat-value"><span class="pulse"></span>ONLINE</div>
                </div>
                <div class="stat">
                    <div class="stat-label">PROTOCOL</div>
                    <div class="stat-value">ANP</div>
                </div>
                <div class="stat">
                    <div class="stat-label">VERSION</div>
                    <div class="stat-value">3.5.1</div>
                </div>
                <div class="stat">
                    <div class="stat-label">MODULES</div>
                    <div class="stat-value">''' + bp_count + '''</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>AVAILABLE ENDPOINTS</h2>
            
            <div class="endpoint-group">
                <h3>System</h3>
                <div class="endpoint"><a href="/health">GET /health →</a></div>
            </div>

            <div class="endpoint-group">
                <h3>Collective Governance (v3)</h3>
                <div class="endpoint"><a href="/api/v3/collective/health">GET /api/v3/collective/health →</a></div>
                <div class="endpoint"><a href="/api/v3/collective/proposals">GET /api/v3/collective/proposals →</a></div>
                <div class="endpoint"><a href="/api/v3/collective/memory">GET /api/v3/collective/memory →</a></div>
            </div>

            <div class="endpoint-group">
                <h3>Legacy APIs</h3>
                <div class="endpoint"><a href="/api/v1/health">GET /api/v1/health →</a></div>
                <div class="endpoint"><a href="/api/v2/status">GET /api/v2/status →</a></div>
            </div>

            <div class="endpoint-group">
                <h3>Admin UI</h3>
                <div class="endpoint"><a href="/admin/">WEB /admin/ →</a></div>
            </div>

            <div class="endpoint-group">
                <h3>Debug</h3>
                <div class="endpoint"><a href="/api/v3/debug/config">GET /api/v3/debug/config →</a></div>
                <div class="endpoint"><a href="/api/v3/debug/test-db">GET /api/v3/debug/test-db →</a></div>
            </div>
        </div>

        <div class="footer">
            Timestamp: ''' + timestamp + ''' | Sapere Aude! - Dare to Know!
        </div>
    </div>
</body>
</html>'''
        return html
    
    @app.route('/health')  
    def health():
        """System health check endpoint"""
        db_status = "DISCONNECTED"
        db_class = "error"
        db_indicator = "disconnected"
        
        try:
            conn = db_manager.get_connection()
            conn.execute("SELECT 1")
            conn.close()
            db_status = "CONNECTED"
            db_class = ""
            db_indicator = ""
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
        
        # Check if client wants JSON
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({
                "status": "operational",
                "database": db_status.lower(),
                "blueprints": blueprints_registered,
                "timestamp": int(time.time())
            })
        
        # Build blueprint list HTML
        bp_html = ""
        for bp in blueprints_registered:
            bp_html += '<div class="blueprint-item">✓ ' + bp + '</div>'
        
        if not bp_html:
            bp_html = '<div class="blueprint-item">No blueprints loaded</div>'
        
        from datetime import datetime
        timestamp_full = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        bp_count = str(len(blueprints_registered))
        timestamp = str(int(time.time()))
        
        # Build HTML - Use string concatenation, NOT f-strings
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AEON NEXUS - Health Status</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #00ff00;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 {
            text-align: center;
            color: #00ff00;
            text-shadow: 0 0 20px #00ff00;
            margin-bottom: 40px;
            font-size: 36px;
        }
        .refresh-notice {
            text-align: center;
            color: #00aa00;
            margin-bottom: 20px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .card {
            background: #111;
            border: 2px solid #00ff00;
            border-radius: 10px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 0 15px rgba(0, 255, 0, 0.3);
        }
        .card.error {
            border-color: #ff0000;
            box-shadow: 0 0 15px rgba(255, 0, 0, 0.3);
        }
        .label {
            color: #00aa00;
            font-size: 14px;
            margin-bottom: 15px;
            text-transform: uppercase;
        }
        .value {
            color: #00ff00;
            font-size: 28px;
            font-weight: bold;
        }
        .card.error .value { color: #ff0000; }
        .pulse {
            display: inline-block;
            width: 15px;
            height: 15px;
            border-radius: 50%;
            background: #00ff00;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }
        .pulse.disconnected {
            background: #ff0000;
            animation: none;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .blueprints {
            background: #111;
            border: 2px solid #00ff00;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 30px;
        }
        h2 { color: #00ff00; margin-bottom: 20px; }
        .blueprint-item {
            background: #0a1a0a;
            padding: 12px 15px;
            margin-bottom: 10px;
            border-left: 3px solid #00ff00;
            border-radius: 3px;
            color: #00aa00;
        }
        .actions { text-align: center; margin-top: 40px; }
        .btn {
            display: inline-block;
            background: #003300;
            color: #00ff00;
            padding: 12px 30px;
            margin: 0 10px;
            border: 2px solid #00ff00;
            border-radius: 5px;
            text-decoration: none;
            transition: all 0.3s;
        }
        .btn:hover {
            background: #004400;
            transform: translateY(-2px);
        }
        .footer {
            text-align: center;
            color: #00aa00;
            font-size: 12px;
            margin-top: 30px;
        }
    </style>
    <script>
        let countdown = 30;
        setInterval(() => {
            countdown--;
            const elem = document.getElementById('countdown');
            if (elem) elem.textContent = countdown;
            if (countdown <= 0) location.reload();
        }, 1000);
    </script>
</head>
<body>
    <div class="container">
        <h1>⚡ SYSTEM HEALTH STATUS ⚡</h1>
        
        <div class="refresh-notice">
            Auto-refresh in <span id="countdown">30</span> seconds
        </div>

        <div class="grid">
            <div class="card">
                <div class="label">System Status</div>
                <div class="value"><span class="pulse"></span>OPERATIONAL</div>
            </div>
            <div class="card ''' + db_class + '''">
                <div class="label">Database</div>
                <div class="value"><span class="pulse ''' + db_indicator + '''"></span>''' + db_status + '''</div>
            </div>
            <div class="card">
                <div class="label">Timestamp</div>
                <div class="value">''' + timestamp + '''</div>
            </div>
            <div class="card">
                <div class="label">Modules</div>
                <div class="value">''' + bp_count + '''</div>
            </div>
        </div>

        <div class="blueprints">
            <h2>📦 Loaded Modules</h2>
            ''' + bp_html + '''
        </div>

        <div class="actions">
            <a href="/" class="btn">← Home</a>
            <a href="/admin/" class="btn">Admin Panel →</a>
            <a href="/api/v3/debug/test-db" class="btn">Run Diagnostics</a>
        </div>

        <div class="footer">
            Last checked: ''' + timestamp_full + '''
        </div>
    </div>
</body>
</html>'''
        return html
    
    @app.route('/api/v3/debug/config')
    def debug_config():
        """Debug endpoint - show configuration"""
        try:
            config_info = {
                "database_path": Config.DATABASE_PATH,
                "database_exists": os.path.exists(Config.DATABASE_PATH),
                "signature_version": getattr(Config, 'SIGNATURE_VERSION', 'unknown'),
                "environment": getattr(Config, 'ENV', 'unknown'),
                "debug_mode": getattr(Config, 'DEBUG', False)
            }
            return jsonify(config_info)
        except Exception as e:
            logger.error(f"Config debug error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/v3/debug/test-db')
    def test_db():
        """Debug endpoint - test database connection"""
        tests = []
        
        # Test 1: File exists
        tests.append({
            "name": "Database file exists",
            "status": os.path.exists(Config.DATABASE_PATH),
            "path": Config.DATABASE_PATH
        })
        
        # Test 2: Connection
        try:
            import sqlite3
            conn = sqlite3.connect(Config.DATABASE_PATH, timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            tests.append({"name": "Database connection", "status": True})
        except Exception as e:
            tests.append({
                "name": "Database connection",
                "status": False,
                "error": str(e)
            })
        
        # Test 3: Tables exist
        try:
            import sqlite3
            conn = sqlite3.connect(Config.DATABASE_PATH, timeout=5)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            tests.append({
                "name": "Database tables",
                "status": len(tables) > 0,
                "tables": tables
            })
        except Exception as e:
            tests.append({
                "name": "Database tables",
                "status": False,
                "error": str(e)
            })
        
        overall_status = "PASS" if all(t.get("status", False) for t in tests) else "FAIL"
        
        return jsonify({
            "overall": overall_status,
            "tests": tests,
            "timestamp": int(time.time())
        })
    
    # =========================================================================
    # ERROR HANDLERS
    # =========================================================================
    
    @app.errorhandler(404)
    def not_found(e):
        """Handle 404 errors"""
        return jsonify({
            "error": "Not found",
            "path": request.path,
            "method": request.method
        }), 404
    
    @app.errorhandler(500)
    def server_error(e):
        """Handle 500 errors"""
        logger.error(f"500 Error: {e}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "details": str(e) if Config.DEBUG else "Enable debug mode for details"
        }), 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle all uncaught exceptions"""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify({
            "error": "Unexpected error",
            "type": type(e).__name__,
            "message": str(e) if Config.DEBUG else "An error occurred"
        }), 500
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    try:
        db_manager.initialize_tables()
        logger.info("✓ Database tables initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        logger.warning("! Application will continue but database may not work correctly")
    
    logger.info("=" * 70)
    logger.info("✓ AEON NEXUS Collective - Application Created")
    logger.info(f"✓ Environment: {getattr(Config, 'ENV', 'unknown')}")
    logger.info(f"✓ Debug Mode: {getattr(Config, 'DEBUG', False)}")
    logger.info(f"✓ Blueprints Loaded: {len(blueprints_registered)}")
    logger.info("=" * 70)
    
    return app

# Create application instance
application = create_app()
app = application

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting development server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)