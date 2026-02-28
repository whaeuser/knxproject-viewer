"""
Public read-only OpenKNXViewer — no bus monitor, no gateway connection.
Safe to expose to the internet.

Run with:
  .venv/bin/uvicorn server_public:app --host 0.0.0.0 --port 8004
"""
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from xknxproject import XKNXProj
from xknxproject.exceptions import InvalidPasswordException, XknxProjectException

INDEX_HTML = Path(__file__).parent / "index.html"
DEMO_PATH = Path(__file__).parent / "demo.knxproj"

app = FastAPI(title="OpenKNXViewer (Public)")

_demo_cache = None


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return {}


@app.get("/api/mode")
def get_mode():
    return {"public": True}


@app.get("/")
async def root():
    return FileResponse(INDEX_HTML)


@app.get("/api/demo/available")
def demo_available():
    return {"available": DEMO_PATH.exists()}


@app.get("/api/demo")
async def get_demo():
    global _demo_cache
    if not DEMO_PATH.exists():
        raise HTTPException(status_code=404, detail="Demo nicht verfügbar")
    if _demo_cache is None:
        try:
            _demo_cache = XKNXProj(path=str(DEMO_PATH)).parse()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Demo konnte nicht geladen werden: {exc}") from exc
    return JSONResponse(content=_demo_cache)


@app.post("/api/parse")
async def parse_project(
    file: UploadFile = File(...),
    password: str = Form(default=""),
    language: str = Form(default="de-DE"),
):
    suffix = Path(file.filename or "project.knxproj").suffix or ".knxproj"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        kwargs: dict = {"path": tmp_path}
        if password:
            kwargs["password"] = password
        if language:
            kwargs["language"] = language

        project = XKNXProj(**kwargs).parse()
        return JSONResponse(content=project)
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=422, detail=f"Invalid password: {exc}") from exc
    except XknxProjectException as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        os.unlink(tmp_path)
