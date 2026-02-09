from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def fix_admin_password():
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        if user:
            print("Found admin user. Updating password...")
            # We explicitly set the hash using the supported method
            user.password_hash = generate_password_hash('admin123', method='pbkdf2:sha256')
            db.session.commit()
            print("Password updated successfully to use pbkdf2:sha256.")
            print("New hash start:", user.password_hash[:20])
        else:
            print("Admin user not found! Creating one...")
            user = User(username='admin')
            user.password_hash = generate_password_hash('admin123', method='pbkdf2:sha256')
            db.session.add(user)
            db.session.commit()
            print("Admin user created with pbkdf2:sha256 password.")

if __name__ == "__main__":
    fix_admin_password()
