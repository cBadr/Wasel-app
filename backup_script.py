import os
import shutil
from datetime import datetime
import sys

def backup_database():
    # Possible locations for the database
    # Priority 1: instance/autodialer.db (Standard Flask)
    # Priority 2: autodialer.db (Root - possibly older versions)
    possible_paths = [
        os.path.join('instance', 'autodialer.db'),
        'autodialer.db'
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
            
    if not db_path:
        print("❌ Error: Could not find 'autodialer.db' in 'instance/' or root directory.")
        return
    
    print(f"✅ Found database at: {db_path}")
    
    # Create backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"backup_autodialer_{timestamp}.db"
    
    try:
        shutil.copy2(db_path, backup_filename)
        print(f"✅ Backup created successfully: {backup_filename}")
        print(f"📂 File size: {os.path.getsize(backup_filename) / 1024:.2f} KB")
        print("\n Now you can save your Database wherever you want'.")
    except Exception as e:
        print(f"❌ Error creating backup: {str(e)}")

if __name__ == "__main__":
    print("--- AutoDialer Database Backup Tool ---")
    backup_database()
    input("\nPress Enter to exit...")
