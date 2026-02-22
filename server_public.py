"""
Public read-only KNX Project Viewer — no bus monitor, no gateway connection.
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

app = FastAPI(title="KNX Project Viewer (Public)")


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return {}


@app.get("/api/mode")
def get_mode():
    return {"public": True}


@app.get("/")
async def root():
    return FileResponse(INDEX_HTML)


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
