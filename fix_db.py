import sqlite3
import os

db_path = os.path.join("instance", "autodialer.db")

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Connected to database.")

# 1. Add test_call_limit to settings
try:
    cursor.execute("ALTER TABLE settings ADD COLUMN test_call_limit INTEGER DEFAULT 1")
    print("Added test_call_limit to settings")
except sqlite3.OperationalError as e:
    print(f"Skipping settings update: {e}")

# 2. Add blocked_by to blacklist
try:
    cursor.execute("ALTER TABLE blacklist ADD COLUMN blocked_by VARCHAR(50)")
    print("Added blocked_by to blacklist")
except sqlite3.OperationalError as e:
    print(f"Skipping blacklist update: {e}")

# 3. Create test_call_history table manually
# We need to match the schema defined in models.py
# id = db.Column(db.Integer, primary_key=True)
# phone_number = db.Column(db.String(20), nullable=False)
# user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
# created_at = db.Column(db.DateTime, default=datetime.utcnow)

create_table_sql = """
CREATE TABLE IF NOT EXISTS test_call_history (
    id INTEGER PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    user_id INTEGER,
    created_at DATETIME,
    FOREIGN KEY(user_id) REFERENCES user(id)
)
"""
try:
    cursor.execute(create_table_sql)
    print("Created test_call_history table")
except sqlite3.OperationalError as e:
    print(f"Error creating table: {e}")

conn.commit()
conn.close()
print("Done.")
