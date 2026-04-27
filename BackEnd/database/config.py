from mongoengine import connect, disconnect
import os

from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("MONGO_HOST")
DB_PORT = os.getenv("MONGO_PORT")
DB_DATABASE = os.getenv("MONGO_DB_NAME")
DB_USERNAME = os.getenv("MONGO_USERNAME")
DB_PASSWORD = os.getenv("MONGO_PASSWORD")


def get_database_uri():
    if DB_USERNAME and DB_PASSWORD:
        return f"mongodb://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}?authSource=admin"
    else:
        return f"mongodb://{DB_HOST}:{DB_PORT}/{DB_DATABASE}"


def connect_database():
    """Conecta ao MongoDB usando MongoEngine"""
    return connect(db=DB_DATABASE, host=get_database_uri())


def disconnect_database():
    """Desconecta do MongoDB"""
    disconnect()
