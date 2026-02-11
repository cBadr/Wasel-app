from app import app, db
from models import Role
import json
import sqlalchemy

def update_admin_permissions():
    print("Starting Admin permissions update...")
    try:
        with app.app_context():
            # Get Admin role
            admin_role = Role.query.filter_by(name='Admin').first()
            if not admin_role:
                print("Admin role not found. Creating 'Admin' role...")
                admin_role = Role(name='Admin')
                db.session.add(admin_role)
            else:
                print("Found 'Admin' role.")
            
            # Define all resources
            resources = ['campaigns', 'contacts', 'monitor', 'settings', 'users', 'roles', 
                         'monitor_queues', 'monitor_trunks', 'monitor_dongles', 'database', 
                         'packages', 'command_screen', 'test_call', 'system_logs', 'cdr_import', 'reports']
            
            # Set 'edit' permission for all resources
            perms = {}
            for res in resources:
                perms[res] = 'edit'
                
            admin_role.set_permissions(perms)
            db.session.commit()
            print("Successfully updated Admin role permissions to full access.")
            print(f"Permissions set: {perms}")
            
    except sqlalchemy.exc.OperationalError as e:
        print("\n[ERROR] Database connection failed!")
        print(f"Details: {e}")
        print("\nPlease check your database credentials in 'app.py'.")
        print("Ensure MySQL is running and the user 'root' with password 'Medoza120a' has access.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")

if __name__ == '__main__':
    update_admin_permissions()
