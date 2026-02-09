import os
import sqlite3
import logging
from datetime import datetime

# إعداد السجل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_database_v3():
    # المسارات
    cwd = os.getcwd()
    instance_dir = os.path.join(cwd, 'instance')
    instance_db = os.path.join(instance_dir, 'autodialer.db')

    if not os.path.exists(instance_db):
        logger.error("Database not found in instance folder!")
        return

    # تحديث قاعدة البيانات
    logger.info("Checking database schema for V3 updates...")
    
    try:
        conn = sqlite3.connect(instance_db)
        cursor = conn.cursor()

        # 1. Create Client Table
        logger.info("Creating client table if not exists...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                company_name VARCHAR(100),
                phone VARCHAR(20) NOT NULL,
                communication_method VARCHAR(20) DEFAULT 'whatsapp',
                address VARCHAR(200),
                notes TEXT,
                created_at DATETIME
            )
        ''')

        # 2. Update User Table
        cursor.execute(f"PRAGMA table_info(user)")
        existing_columns_user = [row[1] for row in cursor.fetchall()]

        if 'client_id' not in existing_columns_user:
            logger.info("Adding column client_id to user...")
            try:
                cursor.execute(f"ALTER TABLE user ADD COLUMN client_id INTEGER REFERENCES client(id)")
            except Exception as e:
                logger.error(f"Error adding client_id: {e}")

        conn.commit()
        conn.close()
        logger.info("Database V3 update completed.")

    except Exception as e:
        logger.error(f"Database update failed: {e}")

if __name__ == "__main__":
    fix_database_v3()
