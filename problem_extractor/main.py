"""실행 진입점: uvicorn problem_extractor.main:app --reload"""

from .api import create_app

app = create_app()
