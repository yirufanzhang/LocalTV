"""把页面上的选择收成方舟请求。和默认值相同的字段不提交。"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field

from localtv.catalog import PIXELS, image_model, video_model

LOCAL_PREFIX = "data-local:"


@dataclass
class Built:
    payload: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def build(kind: str, spec: dict) -> Built:
    if kind == "image":
        return build_image(spec or {})
    if kind == "video":
        return build_video(spec or {})
    return Built(payload={}, errors=["未知的生成类型。"])


def build_image(spec: dict) -> Built:
    out = Built(payload={})
    model = image_model(str(spec.get("model") or ""))
    if not model:
        out.errors.append("请选择一个 Seedream 模型。")
        return out
    if model["retiring"]:
        out.warnings.append(f"{model['name']} 在方舟标记为即将下线。")

    task = str(spec.get("task") or "text")
    if task not in model["tasks"]:
        out.errors.append(f"{model['name']} 不能做「{_task_label(task, 'image')}」。")
        return out

    prompt = str(spec.get("prompt") or "").strip()
    if task != "layers" and not prompt:
        out.errors.append("请写提示词。")
    elif len(prompt) > 300:
        out.warnings.append("中文提示词建议不超过 300 字，过长时模型可能漏掉细节。")

    images = [str(x) for x in (spec.get("images") or []) if str(x).strip()]
    refs = [_inspect(item, "image", out) for item in images]
    if task == "edit" and not images:
        out.errors.append("图生图至少要一张参考图。")
    if task == "layers" and len(images) != 1:
        out.errors.append("图层拆分只能、且必须传入一张图。")
    if images and len(images) > model["maxRefs"]:
        out.errors.append(f"{model['name']} 最多 {model['maxRefs']} 张参考图。")
    if task == "text" and images:
        out.warnings.append(f"已附上 {len(images)} 张参考图，会和提示词一起提交。")

    payload: dict = {"model": _endpoint_or_model(spec, model["id"], out)}
    if prompt:
        payload["prompt"] = prompt
    if images:
        payload["image"] = images[0] if len(images) == 1 else images

    size, size_error = _image_size(model, spec, task)
    if size_error:
        out.errors.append(size_error)
    elif size and _size_should_send(model, spec, task, size):
        payload["size"] = size
        out.warnings.append(f"尺寸将按 {size} 提交。" if "x" in size else f"分辨率档位为 {size}。")

    output = str(spec.get("outputFormat") or model["defaultOutput"])
    if output not in model["outputFormats"]:
        out.errors.append(f"{model['name']} 不能输出 {output}。")
    elif output != model["defaultOutput"]:
        payload["output_format"] = output

    background = spec.get("background")
    if task == "layers":
        if background not in (None, "", model.get("defaultBackground")):
            out.errors.append("图层拆分不能设置透明通道。")
    elif model["backgrounds"]:
        background = str(background or model["defaultBackground"])
        if background not in model["backgrounds"]:
            out.errors.append("这个模型没有该透明通道选项。")
        elif background != model["defaultBackground"]:
            payload["background"] = background
        if background == "transparent" and output == "jpeg":
            out.errors.append("JPEG 不能带透明通道。")
        if background == "transparent" and model["rgba"] == "single-alpha":
            if len(images) != 1:
                out.errors.append("这个模型出透明图时只能有一张参考图。")
            elif images and not _png_has_alpha(images[0]):
                out.errors.append("这个模型出透明图时，参考图必须是带透明通道的 PNG。")
        if background == "transparent" and model["rgba"] == "none":
            out.errors.append("这个模型不能出透明图。")

    optimize = str(spec.get("optimizeMode") or model["defaultOptimize"])
    if optimize not in model["optimizeModes"]:
        out.errors.append(f"{model['name']} 没有「{optimize}」提示词优化。")
    elif optimize != model["defaultOptimize"]:
        payload["optimize_prompt_options"] = {"mode": optimize}

    if bool(spec.get("watermark", True)) != model["defaultWatermark"]:
        payload["watermark"] = bool(spec.get("watermark"))
    elif model["defaultWatermark"]:
        out.warnings.append("图片水印默认开启，右下角会有「AI 生成」。不需要就关掉。")

    response_format = str(spec.get("responseFormat") or "url")
    if response_format not in {"url", "b64_json"}:
        out.errors.append("返回方式只能是链接或 Base64。")
    elif response_format != "url":
        payload["response_format"] = response_format

    if task == "batch":
        payload["sequential_image_generation"] = "auto"
        max_images = _int(spec.get("maxImages"), 15)
        if not 1 <= max_images <= 15:
            out.errors.append("组图张数上限要在 1 到 15 之间。")
        elif len(images) + max_images > 15:
            out.errors.append("参考图张数加上组图张数不能超过 15。")
        if max_images != 15:
            payload["sequential_image_generation_options"] = {"max_images": max_images}
        if bool(spec.get("stream")):
            if not model["stream"]:
                out.errors.append("这个模型不能流式返回。")
            else:
                payload["stream"] = True

    if bool(spec.get("webSearch")):
        if not model["webSearch"]:
            out.errors.append("只有 Seedream 5.0 lite 能联网搜索。")
        else:
            payload["tools"] = [{"type": "web_search"}]
            out.warnings.append("联网搜索会增加等待时间。")

    if task == "layers":
        payload["layer_decomposition"] = True
        options: dict = {}
        if model["layerMax"]:
            layer_max = _int(spec.get("layerMax"), 30)
            if not 2 <= layer_max <= 100:
                out.errors.append("拆分张数上限要在 2 到 100 之间，含底图。")
            elif layer_max != 30:
                options["max_images"] = layer_max
            out.warnings.append("拆分会按张数上限预扣额度，实际张数更少时会退回。")
        if model["ocr"] and bool(spec.get("textRecognition")):
            options["text_recognition"] = True
        if options:
            payload["layer_decomposition_options"] = options

    safety = str(spec.get("safetyIdentifier") or "").strip()
    if safety:
        if not model["safety"]:
            out.errors.append("这个模型没有终端用户标识字段。")
        elif len(safety) > 64 or not safety.isascii():
            out.errors.append("终端用户标识只能是不超过 64 个的英文字符。")
        else:
            payload["safety_identifier"] = safety

    _warn_bytes(refs, out)
    out.payload = payload
    return out


def build_video(spec: dict) -> Built:
    out = Built(payload={})
    model = video_model(str(spec.get("model") or ""))
    if not model:
        out.errors.append("请选择一个 Seedance 模型。")
        return out
    if model["retiring"]:
        out.warnings.append(f"{model['name']} 在方舟标记为即将下线。")

    task = str(spec.get("task") or "text")
    if task not in model["tasks"]:
        out.errors.append(f"{model['name']} 不能做「{_task_label(task, 'video')}」。")
        return out

    prompt = str(spec.get("prompt") or "").strip()
    if task not in {"omni", "draft"} and not prompt:
        out.errors.append("请写提示词。")

    first = str(spec.get("firstFrame") or "").strip()
    last = str(spec.get("lastFrame") or "").strip()
    images = [str(x) for x in (spec.get("images") or []) if str(x).strip()]
    videos = [str(x) for x in (spec.get("videos") or []) if str(x).strip()]
    audios = [str(x) for x in (spec.get("audios") or []) if str(x).strip()]
    draft_id = str(spec.get("draftTaskId") or "").strip()
    allows_refs = model["maxRefImages"] > 0
    if task == "first":
        last = ""
        images, videos, audios = [], [], []
    elif task == "last":
        images, videos, audios = [], [], []
    elif task == "text":
        videos, audios = [], []
        if allows_refs:
            first = ""
            last = ""
        else:
            images = []
            last = ""
    elif task in {"omni", "edit", "extend"}:
        first = ""
        last = ""
    else:
        first = ""
        last = ""
        images, videos, audios = [], [], []
    if task != "draft":
        draft_id = ""

    image_refs = [_inspect(item, "image", out) for item in ([first] if first else []) + ([last] if last else []) + images]
    video_refs = [_inspect(item, "video", out) for item in videos]
    audio_refs = [_inspect(item, "audio", out) for item in audios]

    if task == "first" and not first:
        out.errors.append("首帧生视频需要一张首帧图。")
    if task == "last" and (not first or not last):
        out.errors.append("首尾帧需要首帧和尾帧各一张。")
    if task in {"edit", "extend"} and not videos:
        out.errors.append("这个任务至少要一条参考视频的公网地址。")
    if task == "draft" and not draft_id:
        out.errors.append("请填写样片任务 ID。")
    if task == "omni":
        if not images and not videos and not audios:
            out.errors.append("全模态参考至少要一张图、一条视频或一段音频。")
        elif audios and not images and not videos and not model["audioOnly"]:
            out.errors.append("这个模型不能只传音频，还要有参考图或参考视频。")
        if len(images) > model["maxRefImages"]:
            out.errors.append(f"参考图最多 {model['maxRefImages']} 张。")
        if len(videos) > model["maxRefVideos"]:
            out.errors.append(f"参考视频最多 {model['maxRefVideos']} 条。")
        if len(audios) > model["maxRefAudios"]:
            out.errors.append(f"参考音频最多 {model['maxRefAudios']} 段。")
    if task == "text" and images and len(images) > model["maxRefImages"]:
        out.errors.append(f"参考图最多 {model['maxRefImages']} 张。")
    if task == "text" and images:
        out.warnings.append(f"已附上 {len(images)} 张参考图，会和提示词一起提交。")
    if task in {"edit", "extend", "omni"} and videos and len(videos) > model["maxRefVideos"]:
        out.errors.append(f"参考视频最多 {model['maxRefVideos']} 条。")

    content: list[dict] = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    if first and task in {"first", "last", "text"}:
        content.append({"type": "image_url", "image_url": {"url": first}, "role": "first_frame"})
    if last and task == "last":
        content.append({"type": "image_url", "image_url": {"url": last}, "role": "last_frame"})
    if task in {"omni", "edit", "extend", "text"}:
        for url in images:
            content.append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
    if task in {"omni", "edit", "extend"}:
        for url in videos:
            content.append({"type": "video_url", "video_url": {"url": url}, "role": "reference_video"})
        for url in audios:
            content.append({"type": "audio_url", "audio_url": {"url": url}, "role": "reference_audio"})
    elif task == "draft":
        content.append({"type": "draft_task", "draft_task": {"id": draft_id}})
    if not content and not any("提示词" in item for item in out.errors):
        out.errors.append("没有可提交的内容。")

    payload: dict = {
        "model": _endpoint_or_model(spec, model["id"], out),
        "content": content,
    }

    if task in {"omni", "edit", "extend"}:
        forced = {"edit": "edit", "extend": "extend"}.get(task)
        chosen = forced or str(spec.get("omniType") or "auto")
        if chosen not in {"auto", "reference", "edit", "extend"}:
            out.errors.append("全模态意图只能是自动、参考、编辑或延长。")
        elif chosen != "auto":
            payload["omni_reference_task_type"] = chosen

    draft_on = bool(spec.get("draft")) and task != "draft"
    if draft_on:
        if not model["draft"]:
            out.errors.append("样片模式只有 Seedance 2.5 标准版可以开。")
        else:
            payload["draft"] = True
            payload["resolution"] = "480p"
            out.warnings.append("样片模式只会出 480p 预览。")

    resolution = str(spec.get("resolution") or model["defaultResolution"])
    if draft_on and model["draft"]:
        resolution = "480p"
    if resolution not in model["resolutions"]:
        out.errors.append(f"{model['name']} 没有 {resolution} 这一档分辨率。")
    elif resolution != model["defaultResolution"] and "resolution" not in payload:
        payload["resolution"] = resolution
    if resolution == "1080p" and model["hevc1080"]:
        out.warnings.append("1080p 是 10bit H.265，建议用 VLC、MPV 或 QuickTime 播放。")
    if resolution == "4k" and model["hevc4k"]:
        out.warnings.append("4K 是 10bit H.265，个人账号并发更紧，建议用 VLC、MPV 或 QuickTime 播放。")

    ratio = "adaptive" if task in model["lockRatioTasks"] else str(spec.get("ratio") or model["defaultRatio"])
    if task in model["lockRatioTasks"]:
        payload["ratio"] = "adaptive"
        if str(spec.get("ratio") or model["defaultRatio"]) != "adaptive":
            out.warnings.append("这个任务的宽高比只能跟随素材，已改为 adaptive。")
    elif task == "text" and ratio == "adaptive" and not model["textAdaptive"]:
        out.errors.append("这个模型的文生视频不能选自适应比例。")
    elif ratio not in {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}:
        out.errors.append("宽高比不在可选范围内。")
    elif ratio != model["defaultRatio"]:
        payload["ratio"] = ratio
    if task in {"first", "last"} and ratio != "adaptive":
        out.warnings.append("指定比例和首帧不一致时，方舟会居中裁剪图片。")

    mode = str(spec.get("durationMode") or model["defaultDurationMode"])
    if task in model["lockDurationTasks"]:
        payload["duration"] = -1
        if mode not in {"smart", "omit"}:
            out.warnings.append("编辑任务的时长只能由模型跟随原视频，已改为智能时长。")
    elif mode == "frames":
        if not model["frames"]:
            out.errors.append("只有 Seedance 1.0 能按帧数指定时长。")
        else:
            frames = _int(spec.get("frames"), 0)
            if frames < 29 or frames > 289 or (frames - 25) % 4 != 0:
                out.errors.append("帧数要在 29 到 289 之间，并且等于 25 + 4n。")
            else:
                payload["frames"] = frames
                seconds = frames / 24
                out.warnings.append(f"约 {seconds:.2f} 秒（{frames} 帧 / 24fps）。")
    elif mode == "smart":
        if not model["smartDuration"]:
            out.errors.append("这个模型不能把时长交给模型选择。")
        elif model["defaultDurationMode"] != "smart":
            payload["duration"] = -1
    elif mode == "seconds":
        duration = _int(spec.get("duration"), 0)
        if not model["durationMin"] <= duration <= model["durationMax"]:
            out.errors.append(
                f"时长要在 {model['durationMin']} 到 {model['durationMax']} 秒之间。"
            )
        else:
            payload["duration"] = duration
    elif mode != "omit":
        out.errors.append("时长方式无法识别。")

    if model["generateAudio"]:
        audio_on = spec.get("generateAudio")
        audio_on = model["defaultGenerateAudio"] if audio_on is None else bool(audio_on)
        if audio_on != model["defaultGenerateAudio"]:
            payload["generate_audio"] = audio_on
    elif spec.get("generateAudio") is False:
        out.errors.append("这个模型不能关闭或开启生成声音。")

    if bool(spec.get("watermark", False)) != model["defaultWatermark"]:
        payload["watermark"] = bool(spec.get("watermark"))

    output = str(spec.get("outputFormat") or model["defaultOutput"])
    if output not in model["outputFormats"]:
        out.errors.append(f"{model['name']} 不能输出 {output}。")
    elif output != model["defaultOutput"]:
        payload["output_format"] = output
    if output == "mov":
        out.warnings.append("MOV 适合后期，网页播放器可能打不开，可用 VLC 或 MPV。")

    seed = spec.get("seed")
    if seed not in (None, "", -1, "-1"):
        seed_int = _int(seed, -2)
        if not model["seed"]:
            out.errors.append("只有 Seedance 1.0 能设置种子。")
        elif seed_int < -1 or seed_int > 2_147_483_647:
            out.errors.append("种子要在 -1 到 2147483647 之间。")
        elif seed_int != -1:
            payload["seed"] = seed_int

    if bool(spec.get("cameraFixed")):
        if not model["cameraFixed"]:
            out.errors.append("只有 Seedance 1.0 能固定镜头。")
        elif task == "omni":
            out.errors.append("参考图场景不能固定镜头。")
        else:
            payload["camera_fixed"] = True
            out.warnings.append("固定镜头是追加提示，不保证画面完全不动。")

    if bool(spec.get("returnLastFrame")):
        payload["return_last_frame"] = True

    tier = str(spec.get("serviceTier") or "default")
    if tier != "default":
        if not model["serviceTier"]:
            out.errors.append("离线推理只有 Seedance 1.0 能用。")
        elif tier != "flex":
            out.errors.append("服务等级只能是在线或离线。")
        else:
            payload["service_tier"] = "flex"
            out.warnings.append("离线推理更便宜，等待更久，提交后不能改回在线。")

    priority = _int(spec.get("priority"), 0)
    if priority != 0:
        if not model["priority"] or tier == "flex":
            out.errors.append("当前模型或离线推理不能设置排队优先级。")
        elif not 0 <= priority <= 9:
            out.errors.append("优先级要在 0 到 9 之间。")
        else:
            payload["priority"] = priority

    expires = _int(spec.get("expiresSeconds"), 172800)
    if expires != 172800:
        if not 3600 <= expires <= 259200:
            out.errors.append("任务过期时间要在 1 小时到 72 小时之间。")
        else:
            payload["execution_expires_after"] = expires

    callback = str(spec.get("callbackUrl") or "").strip()
    if callback:
        if not callback.startswith("https://"):
            out.errors.append("回调地址需要是 https 链接。留空则只在本机轮询。")
        else:
            payload["callback_url"] = callback

    if bool(spec.get("webSearch")):
        if not model["webSearch"]:
            out.errors.append("这个模型不能联网搜索。")
        else:
            payload["tools"] = [{"type": "web_search"}]
            out.warnings.append("联网搜索会增加等待时间。")

    safety = str(spec.get("safetyIdentifier") or "").strip()
    if safety:
        if len(safety) > 64 or not safety.isascii():
            out.errors.append("终端用户标识只能是不超过 64 个的英文字符。")
        else:
            payload["safety_identifier"] = safety

    _warn_bytes(image_refs + audio_refs + video_refs, out)
    out.payload = payload
    return out


def redact(value):
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def _image_size(model: dict, spec: dict, task: str) -> tuple[str | None, str | None]:
    if task == "layers":
        tier = str(spec.get("tier") or "auto")
        if tier not in model["layerTiers"]:
            return None, "图层拆分的分辨率不在可选档位里。"
        return tier, None
    mode = str(spec.get("sizeMode") or "tier")
    if mode == "tier":
        tier = str(spec.get("tier") or model["defaultTier"])
        if tier not in model["tiers"]:
            return None, "分辨率档位这个模型没有。"
        return tier, None
    if mode == "ratio":
        tier = str(spec.get("tier") or model["defaultTier"])
        ratio = str(spec.get("ratio") or "1:1")
        table = PIXELS.get(model["profile"], {}).get(tier, {})
        if ratio not in table:
            return None, "这个档位没有对应的比例像素。"
        width, height = table[ratio]
        return f"{width}x{height}", None
    if mode == "custom":
        width = _int(spec.get("width"), 0)
        height = _int(spec.get("height"), 0)
        if width < 2 or height < 2:
            return None, "请填写宽度和高度。"
        pixels = width * height
        aspect = width / height
        if not model["pixelMin"] <= pixels <= model["pixelMax"]:
            return None, (
                f"总像素要在 {model['pixelMin']} 到 {model['pixelMax']} 之间，"
                f"现在是 {pixels}。"
            )
        if not (1 / 16) <= aspect <= 16:
            return None, "宽高比要在 1/16 到 16 之间。"
        return f"{width}x{height}", None
    return None, "尺寸方式无法识别。"


def _size_should_send(model: dict, spec: dict, task: str, size: str) -> bool:
    if task == "layers":
        return size != "auto"
    mode = str(spec.get("sizeMode") or "tier")
    if mode != "tier":
        return True
    return size != model["defaultTier"]


def _endpoint_or_model(spec: dict, model_id: str, out: Built) -> str:
    endpoint = str(spec.get("endpointId") or "").strip()
    if not endpoint:
        return model_id
    out.warnings.append("将使用接入点 ID 调用，参数约束仍按所选模型检查。")
    return endpoint


def _inspect(value: str, kind: str, out: Built) -> dict:
    info = {"kind": kind, "bytes": 0, "placeholder": False, "ok": True}
    if value.startswith(LOCAL_PREFIX):
        info["placeholder"] = True
        info["bytes"] = _local_bytes(value)
        mime = value.split(";", 1)[0].removeprefix(LOCAL_PREFIX)
        if kind == "image" and not mime.startswith("image/"):
            out.errors.append("参考图需要是图片文件。")
            info["ok"] = False
        if kind == "audio" and mime not in {"audio/wav", "audio/mp3", "audio/mpeg"}:
            out.errors.append("参考音频只接受 wav 或 mp3。")
            info["ok"] = False
        if kind == "video":
            out.errors.append("参考视频不能用本机文件，请填公网 URL。")
            info["ok"] = False
    elif value.startswith("data:"):
        info["bytes"] = _data_url_bytes(value)
        header = value.split(",", 1)[0].lower()
        if kind == "image" and not header.startswith("data:image/"):
            out.errors.append("参考图需要是图片。")
            info["ok"] = False
        if kind == "audio" and not (header.startswith("data:audio/wav") or header.startswith("data:audio/mp3") or header.startswith("data:audio/mpeg")):
            out.errors.append("参考音频只接受 wav 或 mp3。")
            info["ok"] = False
        if kind == "video":
            out.errors.append("参考视频只接受公网 URL 或 asset://。")
            info["ok"] = False
        if ";base64" not in header:
            out.errors.append("本地文件需要用 Base64 提交。")
            info["ok"] = False
    elif value.startswith("asset://"):
        return info
    elif value.startswith("https://") or value.startswith("http://"):
        if kind != "image" and value.startswith("http://"):
            out.warnings.append("http 链接可能被方舟拒绝，尽量用 https。")
        return info
    else:
        out.errors.append("素材地址无法识别。图片可以选本地文件，参考视频请填公网 URL。")
        info["ok"] = False
    limit = 30 * 1024 * 1024 if kind == "image" else 15 * 1024 * 1024
    if kind == "audio" and info["bytes"] > limit:
        out.errors.append("单段音频不能超过 15MB。")
        info["ok"] = False
    if kind == "image" and info["bytes"] > limit:
        out.errors.append("单张图片不能超过 30MB。大图不要用 Base64，请先缩小。")
        info["ok"] = False
    return info


def _warn_bytes(refs: list[dict], out: Built) -> None:
    total = sum(item.get("bytes") or 0 for item in refs)
    if total > 48 * 1024 * 1024:
        out.warnings.append("本地素材编码后体积很大，请求体上限约 64MB，过大时请改用公网 URL。")


def _png_has_alpha(value: str) -> bool:
    if value.startswith(LOCAL_PREFIX):
        return "png" in value.split(";", 1)[0] and "alpha=1" in value
    if not value.startswith("data:image/png"):
        return False
    try:
        raw = base64.b64decode(value.split(",", 1)[1][:64] + "==", validate=False)
    except (binascii.Error, IndexError):
        return False
    # PNG 的 color type 在 IHDR 的第 26 个字节附近：签名 8 + 长度 4 + 类型 4 + 宽 4 + 高 4 + bit 1，随后是 color type。
    if len(raw) < 26 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    return raw[25] in {4, 6}


def _data_url_bytes(value: str) -> int:
    try:
        b64 = value.split(",", 1)[1]
    except IndexError:
        return 0
    return int(len(b64) * 3 / 4)


def _local_bytes(value: str) -> int:
    for part in value.split(";"):
        if part.startswith("bytes="):
            return _int(part.split("=", 1)[1], 0)
    return 0


def _redact_str(value: str) -> str:
    if value.startswith("data:"):
        header = value.split(",", 1)[0]
        return f"<{header}; {_data_url_bytes(value)} bytes>"
    if value.startswith(LOCAL_PREFIX):
        return f"<{value}>"
    return value


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _task_label(task: str, kind: str) -> str:
    names = {
        "text": "文生图" if kind == "image" else "文生视频",
        "edit": "图生图" if kind == "image" else "编辑视频",
        "batch": "组图",
        "layers": "图层拆分",
        "first": "首帧",
        "last": "首尾帧",
        "omni": "全模态参考",
        "extend": "延长视频",
        "draft": "样片转正式",
    }
    return names.get(task, task)
