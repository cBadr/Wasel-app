import pymysql
from models import Settings, db
from app import app

# Setup context
ctx = app.app_context()
ctx.push()

settings = Settings.query.first()
print(f"Connecting to CDR DB: {settings.cdr_db_host}...")

try:
    cdr_conn = pymysql.connect(
        host=settings.cdr_db_host,
        port=settings.cdr_db_port,
        user=settings.cdr_db_user,
        password=settings.cdr_db_pass,
        database=settings.cdr_db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with cdr_conn.cursor() as cursor:
        print(f"Checking columns in table '{settings.cdr_table_name}'...")
        cursor.execute(f"DESCRIBE {settings.cdr_table_name}")
        columns = cursor.fetchall()
        for col in columns:
            print(f"Column: {col['Field']} - Type: {col['Type']}")
            
        print("\nChecking first 5 rows to see data:")
        cursor.execute(f"SELECT * FROM {settings.cdr_table_name} LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
except Exception as e:
    print(f"Error: {e}")
