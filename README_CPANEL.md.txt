# ÆON Nexus v3.5.1 - cPanel Deployment

## 1. Forudsætninger
- cPanel med "Setup Python App"
- Python 3.9+
- File Manager

## 2. Upload
1. Log ind i cPanel → File Manager
2. Opret mappen `/home/<brugernavn>/aeon_nexus`
3. Upload hele denne mappe-struktur dertil

## 3. Setup Python App
1. Gå til "Setup Python App"
2. Klik "CREATE APPLICATION"
3. Vælg:
   - Python Version: 3.9
   - Application root: `/home/<brugernavn>/aeon_nexus`
   - Application URL: fx `https://aeonsync.nexus`
   - Application startup file: `wsgi/aeon_wsgi.py`
   - Application Entry point: `application`
4. Gem

## 4. Environment Variables
I samme skærmbillede, tilføj:

- `AEON_MASTER_KEY` = din hemmelige nøgle
- `AEON_SECONDARY_KEY` = din anden nøgle
- `AEON_SYSTEM_KEY` = eventuel systemnøgle
- `FLASK_SECRET_KEY` = lang tilfældig streng

## 5. Installer afhængigheder
I “Setup Python App” → "Run Pip Install" felt:

```text
Flask==2.3.3 Flask-CORS==4.0.0 Flask-Limiter==3.3.3
