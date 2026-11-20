"""密钥留在隐藏配置目录，成片和任务放在文稿里。"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from localtv.catalog import PROVIDERS

_LOCK = threading.Lock()
_MIGRATED = False
_JOB_ID = re.compile(r"^[a-f0-9]{32}$")
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def config_dir() -> Path:
    override = os.environ.get("LOCALTV_HOME", "").strip()
    root = Path(override).expanduser() if override else Path.home() / ".localtv"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_library() -> Path:
    return Path.home() / "Documents" / "LocalTV"


def library_locked() -> bool:
    return bool(os.environ.get("LOCALTV_LIBRARY", "").strip())


def projects_root() -> Path:
    override = os.environ.get("LOCALTV_LIBRARY", "").strip()
    if not override:
        override = str(load_config().get("library_path") or "").strip()
    root = Path(override).expanduser() if override else default_library()
    root.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_projects(root)
    return root


def prepare() -> None:
    config_dir()
    projects_root()


def project_dir() -> Path:
    return projects_root() / current_project_id()


def config_path() -> Path:
    return config_dir() / "config.toml"


def display_path(path: Path | str) -> str:
    resolved = Path(path).expanduser()
    try:
        relative = resolved.resolve().relative_to((Path.home() / "Documents").resolve())
    except ValueError:
        return str(resolved)
    return "文稿/" + relative.as_posix()


def load_config() -> dict:
    path = config_path()
    data = {
        "api_key": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "project_id": "default",
    }
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = _unquote(value.strip())
    providers = data.get("providers")
    if isinstance(providers, str):
        try:
            providers = json.loads(providers)
        except json.JSONDecodeError:
            providers = {}
    data["providers"] = providers if isinstance(providers, dict) else {}
    return data


def save_config(
    api_key: str | None = None,
    base_url: str | None = None,
    clear_key: bool = False,
    project_id: str | None = None,
    library_path: str | None = None,
    providers: dict | None = None,
    clear_provider: str | None = None,
) -> dict:
    with _LOCK:
        return _save_config_unlocked(
            api_key=api_key,
            base_url=base_url,
            clear_key=clear_key,
            project_id=project_id,
            library_path=library_path,
            providers=providers,
            clear_provider=clear_provider,
        )


def _save_config_unlocked(
    api_key: str | None = None,
    base_url: str | None = None,
    clear_key: bool = False,
    project_id: str | None = None,
    library_path: str | None = None,
    providers: dict | None = None,
    clear_provider: str | None = None,
) -> dict:
    current = load_config()
    if clear_key:
        current["api_key"] = ""
        _provider_block(current, "ark")["api_key"] = ""
    elif api_key is not None:
        current["api_key"] = api_key.strip()
        _provider_block(current, "ark")["api_key"] = current["api_key"]
    if base_url is not None and base_url.strip():
        current["base_url"] = base_url.strip().rstrip("/")
        _provider_block(current, "ark")["base_url"] = current["base_url"]
    if providers is not None or clear_provider:
        _apply_providers(current, providers or {}, clear_provider)
    if project_id is not None:
        current["project_id"] = project_id
    if library_path is not None:
        current["library_path"] = library_path
    lines = [
        "# LocalTV 本机配置。不要提交到 git。",
        f"base_url = {json.dumps(current['base_url'], ensure_ascii=False)}",
        f"api_key = {json.dumps(current['api_key'], ensure_ascii=False)}",
        f"project_id = {json.dumps(current.get('project_id') or 'default', ensure_ascii=False)}",
        f"library_path = {json.dumps(current.get('library_path') or '', ensure_ascii=False)}",
        f"providers = {json.dumps(current.get('providers') or {}, ensure_ascii=False)}",
        "",
    ]
    path = config_path()
    path.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(path, 0o600)
    return current


def effective_key() -> tuple[str, str]:
    secret = provider_secret("ark")
    return secret["api_key"], secret["source"]


def provider_secret(provider_id: str) -> dict:
    spec = next((item for item in PROVIDERS if item["id"] == provider_id), None)
    saved = merged_providers().get(provider_id) or {}
    base = str(saved.get("base_url") or (spec or {}).get("defaultBaseUrl") or "").rstrip("/")
    return {
        "api_key": str(saved.get("api_key") or ""),
        "access_key": str(saved.get("access_key") or ""),
        "secret_key": str(saved.get("secret_key") or ""),
        "base_url": base,
        "source": str(saved.get("_source") or ""),
    }


def merged_providers() -> dict:
    cfg = load_config()
    stored = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    result = {}
    for spec in PROVIDERS:
        saved = stored.get(spec["id"]) if isinstance(stored.get(spec["id"]), dict) else {}
        api_key = str(saved.get("api_key") or "")
        base_url = str(saved.get("base_url") or spec["defaultBaseUrl"])
        if spec["id"] == "ark":
            if not api_key:
                api_key = str(cfg.get("api_key") or "")
            if not saved.get("base_url"):
                base_url = str(cfg.get("base_url") or spec["defaultBaseUrl"])
        source = "file" if api_key or saved.get("access_key") or saved.get("secret_key") else ""
        env_key = os.environ.get(spec.get("envKey") or "", "").strip()
        if env_key:
            api_key = env_key
            source = "env"
        result[spec["id"]] = {
            "api_key": api_key,
            "base_url": base_url.rstrip("/"),
            "access_key": str(saved.get("access_key") or ""),
            "secret_key": str(saved.get("secret_key") or ""),
            "_source": source,
        }
    return result


def _provider_block(current: dict, provider_id: str) -> dict:
    stored = current.setdefault("providers", {})
    if not isinstance(stored, dict):
        stored = {}
        current["providers"] = stored
    block = stored.get(provider_id)
    if not isinstance(block, dict):
        block = {}
        stored[provider_id] = block
    return block


def _apply_providers(current: dict, updates: dict, clear_provider: str | None) -> None:
    block = _provider_block(current, "ark")
    block.setdefault("api_key", current.get("api_key") or "")
    block.setdefault("base_url", current.get("base_url") or "")
    if clear_provider:
        target = _provider_block(current, clear_provider)
        target["api_key"] = ""
        target["access_key"] = ""
        target["secret_key"] = ""
    for provider_id, fields in updates.items():
        if not isinstance(fields, dict) or not any(item["id"] == provider_id for item in PROVIDERS):
            continue
        target = _provider_block(current, provider_id)
        api_key = str(fields.get("apiKey") or "").strip()
        access_key = str(fields.get("accessKey") or "").strip()
        secret_key = str(fields.get("secretKey") or "").strip()
        base_url = str(fields.get("baseUrl") or "").strip().rstrip("/")
        if api_key:
            target["api_key"] = api_key
        if access_key:
            target["access_key"] = access_key
        if secret_key:
            target["secret_key"] = secret_key
        if base_url:
            target["base_url"] = base_url
    ark = _provider_block(current, "ark")
    current["api_key"] = str(ark.get("api_key") or "")
    if ark.get("base_url"):
        current["base_url"] = ark["base_url"]


def public_provider_config() -> list[dict]:
    merged = merged_providers()
    items = []
    for spec in PROVIDERS:
        secret = merged[spec["id"]]
        key = secret["api_key"]
        access = secret["access_key"]
        items.append({
            "id": spec["id"],
            "name": spec["name"],
            "hasKey": bool(key),
            "hasAccessKey": bool(access),
            "hasSecret": bool(secret["secret_key"]),
            "keyTail": key[-4:] if len(key) >= 4 else "",
            "accessTail": access[-4:] if len(access) >= 4 else "",
            "keySource": secret["_source"],
            "baseUrl": secret["base_url"],
            "defaultBaseUrl": spec["defaultBaseUrl"],
            "hint": spec["hint"],
            "fields": spec["fields"],
            "envKey": spec.get("envKey") or "",
        })
    return items


def public_config() -> dict:
    cfg = load_config()
    key, source = effective_key()
    tail = key[-4:] if len(key) >= 4 else ""
    return {
        "hasKey": bool(key),
        "keySource": source if key else "",
        "keyTail": tail,
        "baseUrl": provider_secret("ark")["base_url"] or cfg.get("base_url"),
        "providers": public_provider_config(),
        "configPath": str(config_path()),
        "projectId": current_project_id(),
        "projectName": _project_meta(current_project_id()).get("name") or "默认项目",
        "projectPath": str(project_dir()),
        "projectDisplay": display_path(project_dir()),
        "libraryPath": str(projects_root()),
        "libraryDisplay": display_path(projects_root()),
        "libraryLocked": library_locked(),
        "documentsPath": str(Path.home() / "Documents"),
    }


def new_job(kind: str, task: str, model: str, prompt: str, payload: dict) -> dict:
    job = {
        "id": uuid4().hex,
        "kind": kind,
        "task": task,
        "model": model,
        "prompt": prompt,
        "payload": payload,
        "status": "running",
        "remoteId": "",
        "error": "",
        "outputs": [],
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    write_job(job)
    return job


def write_job(job: dict) -> None:
    job["updatedAt"] = _now()
    path = _job_file(job["id"]) or (project_dir() / "jobs" / f"{job['id']}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def read_job(job_id: str) -> dict | None:
    path = _job_file(job_id)
    if path is None:
        return None
    return _with_live_paths(json.loads(path.read_text(encoding="utf-8")))


def list_jobs(project_id: str | None = None) -> list[dict]:
    base = project_dir() if project_id is None else project_path(project_id)
    if base is None:
        return []
    jobs = []
    for path in (base / "jobs").glob("*.json"):
        try:
            jobs.append(_with_live_paths(json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            continue
    jobs.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return jobs[:200]


def active_video() -> dict | None:
    for job in list_jobs():
        if job.get("kind") == "video" and job.get("status") in {"running", "queued"}:
            return job
    return None


def output_dir(job_id: str) -> Path:
    found = _job_file(job_id)
    base = found.parents[1] if found else project_dir()
    path = base / "outputs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_output(job_id: str, name: str) -> Path | None:
    if not _JOB_ID.match(job_id) or not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = (output_dir(job_id) / name).resolve()
    if output_dir(job_id).resolve() not in path.parents:
        return None
    return path if path.exists() else None


def current_project_id() -> str:
    pid = str(load_config().get("project_id") or "default")
    if not _PROJECT_ID.match(pid) or not (projects_root() / pid).exists():
        pid = "default"
    ensure_project(pid, "默认项目" if pid == "default" else None)
    return pid


def project_path(project_id: str) -> Path | None:
    if not _PROJECT_ID.match(project_id):
        return None
    path = projects_root() / project_id
    if not (path / "project.json").exists():
        return None
    return path


def ensure_project(project_id: str, name: str | None = None) -> dict | None:
    if not _PROJECT_ID.match(project_id):
        return None
    path = projects_root() / project_id
    for folder in ("inputs", "outputs", "jobs"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    meta_path = path / "project.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    else:
        meta = {
            "id": project_id,
            "name": name or ("默认项目" if project_id == "default" else project_id),
            "createdAt": _now(),
        }
    meta.setdefault("id", project_id)
    meta.setdefault("name", name or ("默认项目" if project_id == "default" else project_id))
    meta.setdefault("createdAt", _now())
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def create_project(name: str) -> dict | None:
    clean = " ".join(name.split())
    if not clean or len(clean) > 40 or "/" in clean or "\\" in clean:
        return None
    return ensure_project("p" + uuid4().hex[:8], clean)


def set_library(raw: str) -> str | None:
    if library_locked():
        return "存储位置由环境变量 LOCALTV_LIBRARY 决定，页面上不能改。"
    text = raw.strip()
    if not text or "\n" in text or "\x00" in text:
        return "请填写存储位置。"
    new = Path(text).expanduser()
    if not new.is_absolute():
        return "请填写绝对路径，例如 /Users/你的名字/Movies/LocalTV。"
    if new.exists() and not new.is_dir():
        return "存储位置需要是一个文件夹。"
    resolved = new.resolve()
    if resolved in {Path("/").resolve(), Path.home().resolve()}:
        return "请选一个专门的文件夹，不要直接用主目录或磁盘根目录。"
    if resolved in {config_dir().resolve(), config_path().resolve()}:
        return "这个位置存放密钥，不能同时当成片目录。"
    try:
        new.mkdir(parents=True, exist_ok=True)
        probe = new / ".localtv-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return "这个位置无法创建或写入。"
    old = projects_root().resolve()
    resolved = new.resolve()
    if _is_inside(resolved, old) or _is_inside(old, resolved):
        return "新目录不能放在当前存储目录里面，也不能把当前目录包进去。"
    with _LOCK:
        if resolved != old:
            try:
                _relocate_projects(old, resolved)
            except OSError:
                return "搬移现有项目失败，存储位置没有改。"
        _save_config_unlocked(library_path=str(resolved))
    return None


def set_current_project(project_id: str) -> bool:
    if project_path(project_id) is None:
        return False
    save_config(project_id=project_id)
    return True


def public_projects() -> dict:
    current = current_project_id()
    root = projects_root()
    ids = [path.name for path in sorted(root.iterdir()) if path.is_dir() and (path / "project.json").exists()]
    if "default" not in ids:
        ensure_project("default", "默认项目")
        ids.insert(0, "default")
    projects = []
    for project_id in ids:
        meta = _project_meta(project_id)
        jobs = list_jobs(project_id)
        tasks: dict[tuple[str, str], int] = {}
        for job in jobs:
            key = (str(job.get("kind") or ""), str(job.get("task") or ""))
            tasks[key] = tasks.get(key, 0) + 1
        projects.append({
            "id": project_id,
            "name": meta.get("name") or project_id,
            "path": str(root / project_id),
            "current": project_id == current,
            "imageCount": sum(count for (kind, _task), count in tasks.items() if kind == "image"),
            "videoCount": sum(count for (kind, _task), count in tasks.items() if kind == "video"),
            "tasks": [
                {"kind": kind, "task": task, "count": count}
                for (kind, task), count in sorted(tasks.items())
            ],
        })
    return {"current": current, "projects": projects}


def _project_meta(project_id: str) -> dict:
    path = projects_root() / project_id / "project.json"
    if not path.exists():
        return ensure_project(project_id) or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _job_file(job_id: str) -> Path | None:
    if not _JOB_ID.match(str(job_id)):
        return None
    current = project_dir() / "jobs" / f"{job_id}.json"
    if current.exists():
        return current
    root = projects_root()
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        path = folder / "jobs" / f"{job_id}.json"
        if path.exists():
            return path
    return None


def _with_live_paths(job: dict) -> dict:
    job_id = str(job.get("id") or "")
    outputs = []
    for item in job.get("outputs") or []:
        name = str(item.get("name") or "")
        live = safe_output(job_id, name) if name else None
        if live is not None and item.get("path") != str(live):
            item = dict(item)
            item["path"] = str(live)
        outputs.append(item)
    job["outputs"] = outputs
    return job


def _migrate_legacy_projects(root: Path) -> None:
    global _MIGRATED
    with _LOCK:
        if _MIGRATED:
            return
        _MIGRATED = True
        legacy = Path.home() / ".localtv" / "projects"
        if not legacy.is_dir() or root.resolve() == legacy.resolve():
            return
        for child in list(legacy.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            dest = root / child.name
            if not dest.exists():
                shutil.move(str(child), str(dest))
                continue
            for sub in ("jobs", "outputs", "inputs"):
                source_sub = child / sub
                if not source_sub.is_dir():
                    continue
                target_sub = dest / sub
                target_sub.mkdir(parents=True, exist_ok=True)
                for item in list(source_sub.iterdir()):
                    target = target_sub / item.name
                    if not target.exists():
                        shutil.move(str(item), str(target))
        _rewrite_job_paths(root, [str(legacy), str(legacy.resolve())], str(root.resolve()))


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return path.resolve() != parent.resolve()


def _relocate_projects(old: Path, new: Path) -> None:
    new.mkdir(parents=True, exist_ok=True)
    for child in list(old.iterdir()):
        if child.name.startswith("."):
            continue
        dest = new / child.name
        if not dest.exists():
            shutil.move(str(child), str(dest))
            continue
        if child.is_dir() and dest.is_dir():
            _merge_tree(child, dest)
    _rewrite_job_paths(new, [str(old), str(old.resolve())], str(new.resolve()))


def _merge_tree(source: Path, dest: Path) -> None:
    for item in list(source.iterdir()):
        target = dest / item.name
        if not target.exists():
            shutil.move(str(item), str(target))
        elif item.is_dir() and target.is_dir():
            _merge_tree(item, target)


def _rewrite_job_paths(root: Path, old_paths: list[str], new_root: str) -> None:
    for job_file in root.glob("*/jobs/*.json"):
        text = job_file.read_text(encoding="utf-8")
        updated = text
        for old in old_paths:
            updated = updated.replace(old, new_root)
        if updated != text:
            job_file.write_text(updated, encoding="utf-8")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return json.loads(value)
    return value


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
