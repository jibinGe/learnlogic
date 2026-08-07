"""
One-time migration script: add subscription_ends_at column to tutor_profiles table.
Run once from the learnlogic/ directory:
    python add_subscription_ends_at.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE tutor_profiles ADD COLUMN subscription_ends_at TIMESTAMP WITH TIME ZONE"
        ))
        conn.commit()
        print("✅ Column 'subscription_ends_at' added to tutor_profiles.")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
            print("ℹ️  Column already exists — nothing to do.")
        else:
            raise
