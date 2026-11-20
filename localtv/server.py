"""只监听本机的创作页。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from localtv import ark, store
from localtv.ark import ArkError
from localtv.catalog import public_catalog
from localtv.payload import build, redact

WEB = Path(__file__).resolve().parent / "web"
app = FastAPI(title="LocalTV", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/catalog")
def catalog():
    return public_catalog()


@app.get("/api/config")
def read_config():
    store.prepare()
    return store.public_config()


@app.put("/api/config")
def write_config(body: dict = Body(...)):
    base_url = str(body.get("baseUrl") or "").strip().rstrip("/")
    if base_url and not _valid_base(base_url):
        return JSONResponse(
            {"ok": False, "errors": ["火山方舟的接口地址要填到 /api/v3，例如 https://ark.cn-beijing.volces.com/api/v3。"]},
            status_code=400,
        )
    providers = body.get("providers")
    if isinstance(providers, dict):
        for provider_id, fields in providers.items():
            if not isinstance(fields, dict):
                continue
            provider_base = str(fields.get("baseUrl") or "").strip().rstrip("/")
            if provider_base and not _valid_provider_base(provider_id, provider_base):
                return JSONResponse(
                    {"ok": False, "errors": [_base_error(provider_id)]},
                    status_code=400,
                )
    if "libraryPath" in body and not store.library_locked():
        error = store.set_library(str(body.get("libraryPath") or ""))
        if error:
            return JSONResponse({"ok": False, "errors": [error]}, status_code=400)
    api_key = body.get("apiKey")
    store.save_config(
        api_key=None if api_key is None else str(api_key),
        base_url=base_url or None,
        clear_key=bool(body.get("clearKey")),
        providers=providers if isinstance(providers, dict) else None,
        clear_provider=str(body.get("clearProvider") or "") or None,
    )
    return {"ok": True, **store.public_config()}


@app.post("/api/library/pick")
def pick_library():
    if store.library_locked():
        return JSONResponse({"ok": False, "errors": ["存储位置由环境变量 LOCALTV_LIBRARY 决定。"]}, status_code=400)
    if sys.platform != "darwin":
        return JSONResponse({"ok": False, "errors": ["当前系统没有文件夹选择窗口，请直接填写绝对路径。"]}, status_code=400)
    result = subprocess.run(
        ["osascript", "-e", 'POSIX path of (choose folder with prompt "选择 LocalTV 的成片目录")'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return JSONResponse({"ok": False, "errors": ["没有选择文件夹。"]}, status_code=400)
    return {"ok": True, "path": result.stdout.strip().rstrip("/")}


@app.post("/api/preview")
def preview(body: dict = Body(...)):
    built = build(str(body.get("kind") or ""), body.get("spec") or {})
    return {
        "ok": built.ok,
        "errors": built.errors,
        "warnings": built.warnings,
        "payload": redact(built.payload),
    }


@app.post("/api/jobs")
def create_job(body: dict = Body(...)):
    kind = str(body.get("kind") or "")
    spec = body.get("spec") or {}
    built = build(kind, spec)
    if not built.ok:
        return JSONResponse(
            {"ok": False, "errors": built.errors, "warnings": built.warnings, "payload": redact(built.payload)},
            status_code=400,
        )
    if _has_placeholder(built.payload):
        return JSONResponse(
            {"ok": False, "errors": ["本地文件还没读完，请重新选择后再生成。"], "warnings": built.warnings},
            status_code=400,
        )
    try:
        job = ark.run_image(spec, built.payload) if kind == "image" else ark.run_video(spec, built.payload)
    except ArkError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]}, status_code=400)
    _archive_inputs(job["id"], spec)
    failed = job.get("status") == "failed"
    return JSONResponse(
        {"ok": not failed, "job": job, "errors": [job["error"]] if job.get("error") else []},
        status_code=400 if failed else 200,
    )


@app.get("/api/projects")
def projects():
    store.prepare()
    return store.public_projects()


@app.post("/api/projects")
def make_project(body: dict = Body(...)):
    created = store.create_project(str(body.get("name") or ""))
    if not created:
        return JSONResponse({"ok": False, "errors": ["项目名称需要 1 到 40 个字，不能包含斜杠。"]}, status_code=400)
    data = store.public_projects()
    data.update({"ok": True, "created": created["id"]})
    return data


@app.put("/api/projects/current")
def use_project(body: dict = Body(...)):
    if not store.set_current_project(str(body.get("id") or "")):
        return JSONResponse({"ok": False, "errors": ["没有这个项目。"]}, status_code=400)
    return {"ok": True, "config": store.public_config(), **store.public_projects()}


@app.get("/api/projects/{project_id}/jobs")
def project_jobs(project_id: str):
    if store.project_path(project_id) is None:
        return JSONResponse({"ok": False, "errors": ["没有这个项目。"]}, status_code=404)
    return {"jobs": [_public_job(job) for job in store.list_jobs(project_id)]}


@app.get("/api/jobs")
def jobs():
    return {"jobs": [_public_job(job) for job in store.list_jobs()]}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    found = store.read_job(job_id)
    if not found:
        return JSONResponse({"ok": False, "errors": ["没有这条任务。"]}, status_code=404)
    return {"ok": True, "job": _public_job(found)}


@app.post("/api/jobs/{job_id}/sync")
def sync_job(job_id: str):
    found = store.read_job(job_id)
    if not found:
        return JSONResponse({"ok": False, "errors": ["没有这条任务。"]}, status_code=404)
    try:
        found = ark.sync_video(found)
    except ArkError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)], "job": _public_job(found)}, status_code=400)
    return {"ok": True, "job": _public_job(found)}


@app.get("/files/{job_id}/{name}")
def file(job_id: str, name: str):
    path = store.safe_output(job_id, name)
    if path is None:
        return JSONResponse({"ok": False, "errors": ["文件不存在。"]}, status_code=404)
    return FileResponse(path)


@app.post("/api/reveal")
def reveal(body: dict = Body(...)):
    job_id = str(body.get("jobId") or "")
    name = str(body.get("name") or "")
    target = store.safe_output(job_id, name) if name else None
    if target is None:
        folder = store.output_dir(job_id) if store.read_job(job_id) else store.project_dir()
        target = folder if folder.exists() else store.project_dir()
    if sys.platform == "darwin":
        command = _darwin_open(target, str(body.get("mode") or ""))
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            return JSONResponse(
                {"ok": False, "errors": ["没有用本机的 QuickTime 或预览打开。"], "path": str(target)},
                status_code=400,
            )
    return {"ok": True, "path": str(target)}


def _darwin_open(target: Path, mode: str) -> list[str]:
    """用 macOS 自带播放器打开，避免 Parallels 把 mp4 交给 Windows。"""
    if mode != "open":
        return ["open", "-R", str(target)]
    bundle = {
        ".mp4": "com.apple.QuickTimePlayerX",
        ".mov": "com.apple.QuickTimePlayerX",
        ".m4v": "com.apple.QuickTimePlayerX",
        ".png": "com.apple.Preview",
        ".jpg": "com.apple.Preview",
        ".jpeg": "com.apple.Preview",
        ".webp": "com.apple.Preview",
        ".gif": "com.apple.Preview",
    }.get(target.suffix.lower())
    if bundle:
        return ["open", "-b", bundle, "--", str(target)]
    return ["open", "--", str(target)]


def _valid_provider_base(provider_id: str, url: str) -> bool:
    if provider_id == "ark":
        return _valid_base(url)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.query


def _base_error(provider_id: str) -> str:
    if provider_id == "ark":
        return "火山方舟的接口地址要填到 /api/v3，例如 https://ark.cn-beijing.volces.com/api/v3。"
    if provider_id == "minimax":
        return "MiniMax 接口需要是 https 地址。国内用 https://api.minimaxi.com，国际用 https://api.minimax.io。"
    if provider_id == "kling":
        return "可灵接口需要是 https 地址。国内用 https://api-beijing.klingai.com，海外用 https://api-singapore.klingai.com。"
    return "接口地址需要是 https，并且不要带参数。"


def _valid_base(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme == "https":
        allowed = True
    elif parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        allowed = True
    else:
        return False
    path = parsed.path.rstrip("/")
    return allowed and (path == "/api/v3" or path.endswith("/api/v3")) and not parsed.query


def _public_job(job: dict) -> dict:
    shown = dict(job)
    shown.pop("payload", None)
    shown["payload"] = job.get("payload") or {}
    return shown


def _has_placeholder(value) -> bool:
    if isinstance(value, str):
        return value.startswith("data-local:")
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    return False


def _archive_inputs(job_id: str, spec: dict) -> None:
    index = 1
    for item in spec.get("images") or []:
        ark.save_input_copy(job_id, str(item), index)
        index += 1
    for key in ("firstFrame", "lastFrame"):
        if spec.get(key):
            ark.save_input_copy(job_id, str(spec[key]), index)
            index += 1
    for item in spec.get("audios") or []:
        ark.save_input_copy(job_id, str(item), index)
        index += 1
