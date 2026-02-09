from app import app, db, User, Role

def fix_user_roles():
    with app.app_context():
        # 1. Fetch all users
        users = User.query.all()
        print(f"Found {len(users)} users.")
        
        updated_count = 0
        
        for user in users:
            # Check if user has a role assigned via RBAC
            if user.user_role:
                if user.user_role.name == 'Admin':
                    # Ensure legacy role is admin
                    if user.role != 'admin':
                        user.role = 'admin'
                        updated_count += 1
                        print(f"Updated {user.username} legacy role to 'admin'")
                else:
                    # Ensure legacy role is user
                    if user.role != 'user':
                        user.role = 'user'
                        updated_count += 1
                        print(f"Updated {user.username} legacy role to 'user'")
            else:
                # If no role assigned, assume admin if legacy role was admin?
                # Or assume user?
                # Safest is: if username is 'admin', keep as admin.
                # Else set to user.
                if user.username == 'admin':
                     if user.role != 'admin':
                        user.role = 'admin'
                        updated_count += 1
                else:
                     if user.role != 'user':
                        user.role = 'user'
                        updated_count += 1
                        print(f"Updated {user.username} legacy role to 'user' (fallback)")

        db.session.commit()
        print(f"Successfully updated {updated_count} users.")

if __name__ == "__main__":
    fix_user_roles()
