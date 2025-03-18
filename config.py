# config.py
import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env

class Config:
    # Database Settings
    DB_USER = os.getenv("DB_USER", "krishna")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "1122")
    DB_NAME = os.getenv("DB_NAME", "trading_app")
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    
    # FastAPI Settings
    FASTAPI_HOST_PORT = os.getenv("FASTAPI_HOST_PORT", "8666")
    
    # Other Services / API Keys
    PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
    RSSBRIDGE_HOST = os.getenv("RSSBRIDGE_HOST", "192.168.0.122:3333")
    METUBE_URL = os.getenv("METUBE_URL", "http://192.168.0.122:8081")
    NITTER_URL = os.getenv("NITTER_URL", "https://nitter.space")
    
    # Paths
    HOST_YOUTUBE_DATA = os.getenv("HOST_YOUTUBE_DATA", "/mnt/editing/youtube-data")
    PROJECTS_ROOT = os.getenv("PROJECTS_ROOT", "/Users/krishna/Desktop/YouTube/YouTube")
    DAILY_REPORT_DIR = os.getenv("DAILY_REPORT_DIR", "/Volumes/nfsdata/youtube/daily_report")
