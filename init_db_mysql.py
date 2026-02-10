from app import app, db
import sqlalchemy

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Medoza120a@127.0.0.1/wasel'

def init_db():
    with app.app_context():
        try:
            # Try to connect to the database
            with db.engine.connect() as connection:
                print("Successfully connected to the database!")
                
            # Create tables
            print("Creating tables...")
            db.create_all()
            print("Tables created successfully!")
            
        except Exception as e:
            print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_db()
