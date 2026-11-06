from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .main import app

static_dir = Path(__file__).resolve().parents[1] / "static"
if not (static_dir / "index.html").is_file():
    raise RuntimeError(f"Built LeadFlow web files are missing from {static_dir}")

# API routes from main.py are registered before this catch-all web mount.
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="leadflow-web")
