"""调用火山方舟，并把结果下载回本地项目。"""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path

from localtv import store
from localtv.payload import redact

IMAGE_PATH = "/images/generations"
VIDEO_PATH = "/contents/generations/tasks"


class ArkError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def run_image(spec: dict, payload: dict) -> dict:
    key, base = _auth()
    job = store.new_job("image", spec.get("task") or "text", payload["model"], spec.get("prompt") or "", redact(payload))
    try:
        status, ctype, raw = _request("POST", base + IMAGE_PATH, key, payload, timeout=180)
        images = _collect_images(status, ctype, raw)
        if not images:
            raise ArkError("方舟没有返回图片。")
        saved = []
        for index, item in enumerate(images, start=1):
            saved.append(_save_image(job["id"], index, item))
        job["status"] = "succeeded"
        job["outputs"] = saved
        job["error"] = ""
    except Exception as exc:  # noqa: BLE001 - 任务失败要落盘，不能只抛给页面
        job["status"] = "failed"
        job["error"] = _public_error(exc)
    store.write_job(job)
    return job


def run_video(spec: dict, payload: dict) -> dict:
    key, base = _auth()
    running = store.active_video()
    if running:
        raise ArkError("已有一条视频在生成。等它结束再提交，避免打满个人并发。")
    job = store.new_job("video", spec.get("task") or "text", payload["model"], spec.get("prompt") or "", redact(payload))
    try:
        status, _ctype, raw = _request("POST", base + VIDEO_PATH, key, payload, timeout=60)
        body = _json_or_raise(status, raw)
        remote_id = body.get("id") or ""
        if not remote_id:
            raise ArkError("方舟没有返回视频任务 ID。")
        job["remoteId"] = remote_id
        job["status"] = "running"
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = _public_error(exc)
    store.write_job(job)
    return job


def sync_video(job: dict) -> dict:
    if job.get("kind") != "video":
        return job
    if job.get("status") in {"succeeded", "failed", "cancelled"}:
        return job
    if not job.get("remoteId"):
        return job
    key, base = _auth()
    try:
        status, _ctype, raw = _request("GET", f"{base}{VIDEO_PATH}/{job['remoteId']}", key, None, timeout=60)
        body = _json_or_raise(status, raw)
    except Exception as exc:  # noqa: BLE001
        job["error"] = _public_error(exc)
        store.write_job(job)
        return job
    remote = str(body.get("status") or "")
    job["remoteStatus"] = remote
    if remote in {"queued", "running"}:
        job["status"] = remote
        job["error"] = ""
    elif remote == "succeeded":
        content = body.get("content") or {}
        outputs = []
        video_url = content.get("video_url") or ""
        if video_url:
            ext = "mov" if str((job.get("payload") or {}).get("output_format")) == "mov" else "mp4"
            outputs.append(_download(job["id"], f"video.{ext}", video_url, "video"))
        frame = content.get("last_frame_url") or ""
        if frame:
            outputs.append(_download(job["id"], "last-frame.jpeg", frame, "image"))
        job["outputs"] = outputs
        job["status"] = "succeeded"
        job["error"] = ""
        usage = body.get("usage")
        if usage:
            job["usage"] = usage
    elif remote in {"failed", "expired", "cancelled"}:
        job["status"] = "expired" if remote == "expired" else "failed"
        error = body.get("error") or {}
        job["error"] = error.get("message") or f"任务{remote}。"
    else:
        job["status"] = "running"
    store.write_job(job)
    return job


def _auth() -> tuple[str, str]:
    secret = store.provider_secret("ark")
    if not secret["api_key"]:
        raise ArkError("还没有火山方舟 API Key。先在设置里保存。")
    return secret["api_key"], secret["base_url"] or "https://ark.cn-beijing.volces.com/api/v3"


def _request(method: str, url: str, key: str, payload: dict | None, timeout: int) -> tuple[int, str, bytes]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "localtv/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except urllib.error.URLError as exc:
        raise ArkError(f"连不上火山方舟：{exc.reason}") from exc


def _json_or_raise(status: int, raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ArkError(f"方舟返回了无法解析的内容（HTTP {status}）。") from exc
    if status >= 400 or body.get("error"):
        error = body.get("error") or {}
        message = error.get("message") or body.get("message") or f"请求失败（HTTP {status}）。"
        raise ArkError(_friendly(message, error.get("code") or ""), status)
    return body


def _collect_images(status: int, ctype: str, raw: bytes) -> list[dict]:
    if "text/event-stream" in ctype:
        found: list[dict] = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                _walk_images(json.loads(chunk), found)
            except json.JSONDecodeError:
                continue
        if not found:
            raise ArkError("流式响应里没有图片。")
        return found
    body = _json_or_raise(status, raw)
    found = []
    _walk_images(body.get("data") or [], found)
    return found


def _walk_images(node, found: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("url") or node.get("b64_json"):
            found.append(node)
            return
        for value in node.values():
            _walk_images(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_images(item, found)


def _save_image(job_id: str, index: int, item: dict) -> dict:
    ext = "png" if str(item.get("output_format") or "").lower() == "png" else "png"
    if str(item.get("output_format") or "").lower() == "jpeg":
        ext = "jpg"
    name = f"image-{index:02d}.{ext}"
    if item.get("b64_json"):
        path = store.output_dir(job_id) / name
        path.write_bytes(base64.b64decode(item["b64_json"]))
        return _file_record(job_id, name, "image")
    url = item.get("url") or ""
    if not url:
        raise ArkError("某张图片没有下载地址。")
    guessed = _ext_from_url(url) or ext
    name = f"image-{index:02d}.{guessed}"
    return _download(job_id, name, url, "image")


def _download(job_id: str, name: str, url: str, kind: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "localtv/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.URLError as exc:
        raise ArkError(f"结果下载失败：{exc.reason}") from exc
    suffix = mimetypes.guess_extension(ctype.split(";")[0].strip() or "")
    if suffix and not name.endswith(suffix):
        # 保留调用方给的扩展名，避免视频被猜成 .bin。
        pass
    path = store.output_dir(job_id) / name
    path.write_bytes(data)
    return _file_record(job_id, name, kind)


def _file_record(job_id: str, name: str, kind: str) -> dict:
    path = store.output_dir(job_id) / name
    return {
        "name": name,
        "kind": kind,
        "path": str(path),
        "url": f"/files/{job_id}/{name}",
    }


def _ext_from_url(url: str) -> str:
    clean = url.split("?", 1)[0].lower()
    for ext in ("png", "jpg", "jpeg", "webp"):
        if clean.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ext
    return ""


def _friendly(message: str, code: str) -> str:
    text = message or "请求失败。"
    lowered = text.lower()
    if "authentication" in lowered or "unauthorized" in lowered or code.startswith("Authentication"):
        return "API Key 无效或没有权限。请到火山方舟检查密钥，并确认模型已开通。"
    if "Sensitive" in code or "sensitive" in lowered or "审核" in text:
        return f"内容没有通过审核。{text}"
    if "quota" in lowered or "rate" in lowered or "限流" in text:
        return f"额度或频率到顶了。稍后再试。{text}"
    return text


def _public_error(exc: Exception) -> str:
    if isinstance(exc, ArkError):
        return str(exc)
    return f"生成失败：{exc}"


def save_input_copy(job_id: str, data_url: str, index: int) -> None:
    if not data_url.startswith("data:") or "," not in data_url:
        return
    header, b64 = data_url.split(",", 1)
    ext = "bin"
    if "image/png" in header:
        ext = "png"
    elif "image/jpeg" in header:
        ext = "jpg"
    elif "image/webp" in header:
        ext = "webp"
    elif "audio/wav" in header:
        ext = "wav"
    elif "audio/mp" in header:
        ext = "mp3"
    path = store.project_dir() / "inputs" / f"{job_id}-{index}.{ext}"
    try:
        path.write_bytes(base64.b64decode(b64))
    except ValueError:
        return
