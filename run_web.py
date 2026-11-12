"""Start the local web app: python run_web.py  ->  http://127.0.0.1:8110

File viewing, format support, the unknown-file inspector, the format database, the docs and the BM25 workspace search
run on TextView's Python code. The chat agent and other LLM features stay in the desktop app (python main.py).
"""
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    print("TextView web app: http://127.0.0.1:8110")
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=8110)
