"""Vercel Python 함수 진입점: 모든 경로를 Flask 앱으로 넘긴다 (vercel.json rewrites)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()
