import os
import sqlite3
import logging

# إعداد السجل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_database_v2():
    # المسارات
    cwd = os.getcwd()
    instance_dir = os.path.join(cwd, 'instance')
    instance_db = os.path.join(instance_dir, 'autodialer.db')

    if not os.path.exists(instance_db):
        logger.error("Database not found in instance folder!")
        return

    # تحديث قاعدة البيانات
    logger.info("Checking database schema for V2 updates...")
    
    try:
        conn = sqlite3.connect(instance_db)
        cursor = conn.cursor()

        # 1. Update User Table
        cursor.execute(f"PRAGMA table_info(user)")
        existing_columns_user = [row[1] for row in cursor.fetchall()]

        if 'is_banned' not in existing_columns_user:
            logger.info("Adding column is_banned to user...")
            try:
                cursor.execute(f"ALTER TABLE user ADD COLUMN is_banned BOOLEAN DEFAULT 0")
            except Exception as e:
                logger.error(f"Error adding is_banned: {e}")

        # 2. Update Campaign Table
        cursor.execute(f"PRAGMA table_info(campaign)")
        existing_columns_campaign = [row[1] for row in cursor.fetchall()]

        if 'user_id' not in existing_columns_campaign:
            logger.info("Adding column user_id to campaign...")
            try:
                cursor.execute(f"ALTER TABLE campaign ADD COLUMN user_id INTEGER REFERENCES user(id)")
                # Set default user_id to 1 (Assuming 1 is Admin) for existing campaigns
                cursor.execute("UPDATE campaign SET user_id = 1 WHERE user_id IS NULL")
            except Exception as e:
                logger.error(f"Error adding user_id: {e}")

        if 'is_locked' not in existing_columns_campaign:
            logger.info("Adding column is_locked to campaign...")
            try:
                cursor.execute(f"ALTER TABLE campaign ADD COLUMN is_locked BOOLEAN DEFAULT 0")
            except Exception as e:
                logger.error(f"Error adding is_locked: {e}")

        conn.commit()
        conn.close()
        logger.info("Database V2 update completed.")

    except Exception as e:
        logger.error(f"Database update failed: {e}")

if __name__ == "__main__":
    fix_database_v2()
