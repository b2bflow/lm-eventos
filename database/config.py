from mongoengine import connect, disconnect
import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "27017")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")


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
