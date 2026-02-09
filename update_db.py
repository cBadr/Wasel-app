from app import app, db
from models import Blacklist

with app.app_context():
    db.create_all()
    print("Database updated.")
