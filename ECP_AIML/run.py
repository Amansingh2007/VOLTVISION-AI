"""Run the merged VoltVision AI application (FastAPI backend + integrated frontend)."""
import os
import sys
from pathlib import Path
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print("=" * 65)
    print(" [VoltVision AI] Merged Frontend & Backend ML Application")
    print("=" * 65)
    print(f" Web Application: http://{host}:{port}/")
    print(f" Login Portal:    http://{host}:{port}/login.html")
    print(f" API Docs:        http://{host}:{port}/docs")
    print("=" * 65)
    uvicorn.run("main:app", host=host, port=port, reload=True, app_dir=str(BACKEND_DIR))
