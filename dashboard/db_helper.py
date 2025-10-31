"""
Database helper for dashboard modules.
Import this instead of directly using sqlite3.
"""
import sys
import os

# Add parent src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import PodcastDatabase

def get_db():
    """Get database instance using PostgreSQL."""
    return PodcastDatabase()

def get_connection():
    """Get raw database connection for custom queries."""
    db = get_db()
    return db._get_connection()
