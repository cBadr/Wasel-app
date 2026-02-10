from sqlalchemy import create_engine, text

# Configuration
DB_URI = 'mysql+pymysql://root:Medoza120a@127.0.0.1/wasel'

def fix_db():
    print(f"Connecting to {DB_URI}...")
    try:
        engine = create_engine(DB_URI)
        with engine.connect() as conn:
            print("Connected successfully.")
            
            # Check if column exists
            print("Checking for 'updated_at' column in 'campaign' table...")
            result = conn.execute(text("SHOW COLUMNS FROM campaign LIKE 'updated_at'"))
            if result.fetchone():
                print("Column 'updated_at' already exists.")
            else:
                print("Column missing. Adding 'updated_at'...")
                # Add the column
                conn.execute(text("ALTER TABLE campaign ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                print("Column 'updated_at' added successfully.")
                
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fix_db()
