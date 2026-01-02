import sys
import os

# Set absolute path (CHANGE THIS TO YOUR ACTUAL PATH)
project_home = '/home/superral/aeon_nexus'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import application from main.py
# This should work cleanly now that main.py doesn't print in global scope
from main import application
