#!/usr/bin/env python3
"""
Database initialization script.

Creates all tables and seeds the test user for development.
Run this script to initialize a fresh database.
"""

import sys
import os

# Add the parent directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uuid import UUID
from datetime import datetime

from db.base import Base
from db.session import engine, SessionLocal

# Import all models to register them with Base.metadata
from db.models.user import User
from db.models.channel import Channel
from db.models.chat_session import ChatSession
from db.models.analytics_snapshot import AnalyticsSnapshot
from db.models.video_snapshot import VideoSnapshot
from db.models.weekly_insight import WeeklyInsight


# Test user ID used by the frontend for development
TEST_USER_ID = UUID('00000000-0000-0000-0000-000000000001')


def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully")


def seed_test_user():
    """Insert the test user if not exists."""
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.id == TEST_USER_ID).first()
        
        if existing_user:
            print(f"✓ Test user already exists: {existing_user.email}")
            return
        
        test_user = User(
            id=TEST_USER_ID,
            email='test@contexthub.dev',
            name='Test User',
            plan='free',
            created_at=datetime.utcnow(),
        )
        db.add(test_user)
        db.commit()
        print(f"✓ Test user created: {test_user.email}")
    
    except Exception as e:
        db.rollback()
        print(f"✗ Failed to seed test user: {e}")
        raise
    finally:
        db.close()


def main():
    """Initialize the database with all tables and seed data."""
    print("=" * 50)
    print("Database Initialization")
    print("=" * 50)
    
    try:
        create_tables()
        seed_test_user()
        print("=" * 50)
        print("✓ Database initialized successfully!")
        print("=" * 50)
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
