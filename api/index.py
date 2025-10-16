import sys
import os

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the complete Flask app from server.py
from server import app

# Export for Vercel - this is what Vercel will use as the handler
handler = app