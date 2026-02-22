import tempfile
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from xknxproject import XKNXProj
from xknxproject.exceptions import InvalidPasswordException, XknxProjectException

app = FastAPI(title="KNX Project Viewer")

INDEX_HTML = Path(__file__).parent / "index.html"


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return {}


@app.get("/")
async def root():
    return FileResponse(INDEX_HTML)


@app.post("/api/parse")
async def parse_project(
    file: UploadFile = File(...),
    password: str = Form(default=""),
    language: str = Form(default=""),
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
