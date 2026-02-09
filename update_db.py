from app import app, db
from models import Settings, Blacklist, TestCallHistory
from sqlalchemy import text

with app.app_context():
    print("Updating database schema...")
    
    # 1. Add test_call_limit to settings if not exists
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN test_call_limit INTEGER DEFAULT 1"))
            print("Added test_call_limit to settings")
    except Exception as e:
        print(f"Skipping settings update (might exist): {e}")

    # 2. Add blocked_by to blacklist if not exists
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE blacklist ADD COLUMN blocked_by VARCHAR(50)"))
            print("Added blocked_by to blacklist")
    except Exception as e:
        print(f"Skipping blacklist update (might exist): {e}")

    # 3. Create test_call_history table
    try:
        db.create_all()
        print("Created new tables (TestCallHistory)")
    except Exception as e:
        print(f"Error creating tables: {e}")

    print("Database update complete.")
