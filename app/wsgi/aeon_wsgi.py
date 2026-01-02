import sys
import os

# Sørg for at projektroden er i path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Importér Flask-app'en
from main import app as application
