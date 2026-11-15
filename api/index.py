"""Vercel entry point: re-export the FastAPI app from services/api/main.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api.main import app  # noqa: E402,F401
