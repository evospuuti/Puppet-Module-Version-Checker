import sys
import os

# Add parent directory to path to import server module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app

# This is the handler that Vercel will call
handler = app