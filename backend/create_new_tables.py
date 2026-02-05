from src.core.database import sync_engine
from src.models.models import UserModelAccess
from sqlalchemy import inspect

def create_new_tables():
    inspector = inspect(sync_engine)
    if not inspector.has_table("user_model_access"):
        print("Creating table user_model_access...")
        UserModelAccess.__table__.create(bind=sync_engine)
        print("Table user_model_access created successfully.")
    else:
        print("Table user_model_access already exists.")

if __name__ == "__main__":
    create_new_tables()
