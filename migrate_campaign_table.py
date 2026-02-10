
import pymysql

# Configuration - Trying remote since local failed
DB_HOST = '197.56.208.57' 
DB_USER = 'root'
DB_PASS = 'Medoza120a'
DB_NAME = 'wasel'

def migrate():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10
        )
        print(f"Connected to database at {DB_HOST}.")
        
        with conn.cursor() as cursor:
            # Check if columns exist to avoid errors
            cursor.execute("DESCRIBE campaign")
            columns = [row['Field'] for row in cursor.fetchall()]
            
            alter_statements = []
            
            if 'start_date' not in columns:
                alter_statements.append("ADD COLUMN start_date DATE NULL")
            
            if 'end_date' not in columns:
                alter_statements.append("ADD COLUMN end_date DATE NULL")
                
            if 'daily_start_time' not in columns:
                alter_statements.append("ADD COLUMN daily_start_time TIME NULL")
                
            if 'daily_end_time' not in columns:
                alter_statements.append("ADD COLUMN daily_end_time TIME NULL")
                
            if 'concurrent_channels' not in columns:
                alter_statements.append("ADD COLUMN concurrent_channels INT NULL")
                
            if 'max_retries' not in columns:
                alter_statements.append("ADD COLUMN max_retries INT NULL")
                
            if 'retry_interval' not in columns:
                alter_statements.append("ADD COLUMN retry_interval INT NULL")
            
            if alter_statements:
                sql = f"ALTER TABLE campaign {', '.join(alter_statements)}"
                print(f"Executing: {sql}")
                cursor.execute(sql)
                conn.commit()
                print("Migration successful.")
            else:
                print("No migration needed. Columns already exist.")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.open:
            conn.close()

if __name__ == "__main__":
    migrate()
