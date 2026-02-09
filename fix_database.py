import os
import shutil
import sqlite3
import logging

# إعداد السجل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_database():
    # المسارات
    cwd = os.getcwd()
    instance_dir = os.path.join(cwd, 'instance')
    root_db = os.path.join(cwd, 'autodialer.db')
    instance_db = os.path.join(instance_dir, 'autodialer.db')

    # 1. التأكد من وجود مجلد instance
    if not os.path.exists(instance_dir):
        logger.info(f"Creating instance directory: {instance_dir}")
        os.makedirs(instance_dir)

    # 2. نقل قاعدة البيانات من الجذر إلى instance إذا لزم الأمر
    if os.path.exists(root_db):
        if not os.path.exists(instance_db):
            logger.info("Moving database from root to instance folder...")
            shutil.move(root_db, instance_db)
            logger.info("Database moved successfully.")
        else:
            logger.warning("Database exists in BOTH root and instance folder.")
            logger.warning(f"Keeping the one in instance folder: {instance_db}")
            logger.warning(f"You may want to manually backup and delete: {root_db}")
    else:
        if not os.path.exists(instance_db):
            logger.info("No database found. A new one will be created by the app.")
            return

    # 3. تحديث قاعدة البيانات (Migration)
    logger.info("Checking database schema...")
    
    # القوائم المطلوب إضافتها
    columns_to_add_settings = [
        ('ami_host', 'VARCHAR(50) DEFAULT "127.0.0.1"'),
        ('ami_port', 'INTEGER DEFAULT 5038'),
        ('ami_user', 'VARCHAR(50) DEFAULT "admin"'),
        ('ami_secret', 'VARCHAR(50) DEFAULT "amp111"'),
        # ('target_queue', 'VARCHAR(10) DEFAULT "501"'), # Moved to Campaign
        ('dial_delay', 'INTEGER DEFAULT 5'),
        ('cdr_db_host', 'VARCHAR(50) DEFAULT "127.0.0.1"'),
        ('cdr_db_port', 'INTEGER DEFAULT 3306'),
        ('cdr_db_user', 'VARCHAR(50) DEFAULT "root"'),
        ('cdr_db_pass', 'VARCHAR(50) DEFAULT ""'),
        ('cdr_db_name', 'VARCHAR(50) DEFAULT "asteriskcdrdb"'),
        ('cdr_table_name', 'VARCHAR(50) DEFAULT "cdr"'),
        ('telegram_bot_token', 'VARCHAR(100)'),
        ('telegram_chat_id', 'VARCHAR(50)'),
        ('telegram_notify_start_stop', 'BOOLEAN DEFAULT 1'),
        ('telegram_notify_progress', 'BOOLEAN DEFAULT 1'),
        ('telegram_notify_each_call', 'BOOLEAN DEFAULT 0'),
        ('telegram_notify_interval', 'INTEGER DEFAULT 30'),
        ('retry_interval', 'INTEGER DEFAULT 60'),
        ('max_retries', 'INTEGER DEFAULT 3')
    ]

    columns_to_add_contact = [
        ('retries', 'INTEGER DEFAULT 0'),
        ('duration', 'INTEGER DEFAULT 0')
    ]

    columns_to_add_campaign = [
        ('target_queue', 'VARCHAR(10) DEFAULT "501"')
    ]

    try:
        conn = sqlite3.connect(instance_db)
        cursor = conn.cursor()

        # --- Settings Table ---
        cursor.execute(f"PRAGMA table_info(settings)")
        existing_columns_settings = [row[1] for row in cursor.fetchall()]

        for col_name, col_def in columns_to_add_settings:
            if col_name not in existing_columns_settings:
                print(f"Adding column {col_name} to settings...")
                try:
                    cursor.execute(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    print(f"Error adding {col_name}: {e}")

        # --- Contact Table ---
        cursor.execute(f"PRAGMA table_info(contact)")
        existing_columns_contact = [row[1] for row in cursor.fetchall()]

        for col_name, col_def in columns_to_add_contact:
            if col_name not in existing_columns_contact:
                print(f"Adding column {col_name} to contact...")
                try:
                    cursor.execute(f"ALTER TABLE contact ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    print(f"Error adding {col_name}: {e}")

        # --- Campaign Table ---
        cursor.execute(f"PRAGMA table_info(campaign)")
        existing_columns_campaign = [row[1] for row in cursor.fetchall()]

        for col_name, col_def in columns_to_add_campaign:
            if col_name not in existing_columns_campaign:
                print(f"Adding column {col_name} to campaign...")
                try:
                    cursor.execute(f"ALTER TABLE campaign ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    print(f"Error adding {col_name}: {e}")

        # --- User Table ---
        # إنشاء جدول المستخدمين إذا لم يكن موجوداً
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        if not cursor.fetchone():
            print("Creating user table...")
            cursor.execute('''
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(128) NOT NULL,
                    role VARCHAR(20) DEFAULT 'admin'
                )
            ''')
            
        # --- Role Table ---
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='role'")
        if not cursor.fetchone():
            print("Creating role table...")
            cursor.execute('''
                CREATE TABLE role (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(50) UNIQUE NOT NULL,
                    permissions TEXT DEFAULT '{}'
                )
            ''')
            # Create default Admin role
            import json
            admin_perms = json.dumps({
                'campaigns': 'edit',
                'contacts': 'edit',
                'monitor': 'view',
                'settings': 'edit',
                'users': 'edit',
                'roles': 'edit'
            })
            cursor.execute("INSERT INTO role (name, permissions) VALUES (?, ?)", ('Admin', admin_perms))

        # --- Update User Table with role_id ---
        cursor.execute(f"PRAGMA table_info(user)")
        existing_columns_user = [row[1] for row in cursor.fetchall()]
        
        if 'role_id' not in existing_columns_user:
            print("Adding column role_id to user...")
            cursor.execute("ALTER TABLE user ADD COLUMN role_id INTEGER REFERENCES role(id)")
            
            # Update existing admin users to have role_id of Admin role
            # Get Admin role ID
            cursor.execute("SELECT id FROM role WHERE name='Admin'")
            admin_role = cursor.fetchone()
            if admin_role:
                admin_role_id = admin_role[0]
                cursor.execute("UPDATE user SET role_id = ? WHERE role='admin'", (admin_role_id,))

        conn.commit()

        conn.close()
        logger.info("Database migration completed successfully.")

    except Exception as e:
        logger.error(f"Error during migration: {e}")

if __name__ == "__main__":
    fix_database()
