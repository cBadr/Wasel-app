import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Settings

# Use absolute path for DB
db_path = f'sqlite:///{os.path.join(os.getcwd(), "instance", "autodialer.db")}'
engine = create_engine(db_path)
Session = sessionmaker(bind=engine)
session = Session()

try:
    settings = session.query(Settings).first()
    if not settings:
        settings = Settings()
        session.add(settings)
    
    settings.telegram_bot_token = "8465760307:AAGkPIDf0bFmzpL3GSt9DBcwZOhYzmrR8jA"
    settings.telegram_chat_id = "5154061728"
    
    session.commit()
    print("Settings updated successfully.")
except Exception as e:
    print(f"Error updating settings: {e}")
finally:
    session.close()
