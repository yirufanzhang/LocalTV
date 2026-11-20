"""Seedream / Seedance 能力目录。页面和请求校验都读这里。"""

from __future__ import annotations

RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]
VIDEO_RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]

# 档位 + 比例 -> 文档给出的参考像素。自定义宽高不走这张表。
PIXELS: dict[str, dict[str, dict[str, tuple[int, int]]]] = {
    "s55": {
        "1K": {
            "1:1": (1024, 1024), "4:3": (1152, 864), "3:4": (864, 1152),
            "16:9": (1424, 800), "9:16": (800, 1424), "3:2": (1248, 832),
            "2:3": (832, 1248), "21:9": (1568, 672),
        },
        "1.5K": {
            "1:1": (1536, 1536), "4:3": (1792, 1344), "3:4": (1344, 1792),
            "16:9": (2048, 1152), "9:16": (1152, 2048), "3:2": (1872, 1248),
            "2:3": (1248, 1872), "21:9": (2352, 1008),
        },
        "2K": {
            "1:1": (2048, 2048), "4:3": (2368, 1776), "3:4": (1776, 2368),
            "16:9": (2816, 1584), "9:16": (1584, 2816), "3:2": (2496, 1664),
            "2:3": (1664, 2496), "21:9": (3136, 1344),
        },
    },
    "lite": {
        "2K": {
            "1:1": (2048, 2048), "4:3": (2304, 1728), "3:4": (1728, 2304),
            "16:9": (2848, 1600), "9:16": (1600, 2848), "3:2": (2496, 1664),
            "2:3": (1664, 2496), "21:9": (3136, 1344),
        },
        "3K": {
            "1:1": (3072, 3072), "4:3": (3456, 2592), "3:4": (2592, 3456),
            "16:9": (4096, 2304), "9:16": (2304, 4096), "3:2": (3744, 2496),
            "2:3": (2496, 3744), "21:9": (4704, 2016),
        },
        "4K": {
            "1:1": (4096, 4096), "4:3": (4704, 3520), "3:4": (3520, 4704),
            "16:9": (5504, 3040), "9:16": (3040, 5504), "3:2": (4992, 3328),
            "2:3": (3328, 4992), "21:9": (6240, 2656),
        },
    },
    "s40": {
        "1K": {
            "1:1": (1024, 1024), "4:3": (1152, 864), "3:4": (864, 1152),
            "16:9": (1280, 720), "9:16": (720, 1280), "3:2": (1248, 832),
            "2:3": (832, 1248), "21:9": (1512, 648),
        },
        "2K": {
            "1:1": (2048, 2048), "4:3": (2304, 1728), "3:4": (1728, 2304),
            "16:9": (2848, 1600), "9:16": (1600, 2848), "3:2": (2496, 1664),
            "2:3": (1664, 2496), "21:9": (3136, 1344),
        },
        "4K": {
            "1:1": (4096, 4096), "4:3": (4704, 3520), "3:4": (3520, 4704),
            "16:9": (5504, 3040), "9:16": (3040, 5504), "3:2": (4992, 3328),
            "2:3": (3328, 4992), "21:9": (6240, 2656),
        },
    },
}
PIXELS["s45"] = {"2K": PIXELS["lite"]["2K"], "4K": PIXELS["lite"]["4K"]}

IMAGE_TASKS = [
    {"id": "text", "label": "文生图"},
    {"id": "edit", "label": "图生图"},
    {"id": "batch", "label": "组图"},
    {"id": "layers", "label": "图层拆分"},
]
PROVIDERS = [
    {
        "id": "ark",
        "name": "火山方舟",
        "envKey": "ARK_API_KEY",
        "defaultBaseUrl": "https://ark.cn-beijing.volces.com/api/v3",
        "fields": ["apiKey", "baseUrl"],
        "hint": "在火山引擎控制台的方舟里创建。接口填到 /api/v3，不要填具体的图片或视频地址。",
        "series": [
            {"id": "seedream", "name": "Seedream", "kind": "image"},
            {"id": "seedance", "name": "Seedance", "kind": "video"},
        ],
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "envKey": "MINIMAX_API_KEY",
        "defaultBaseUrl": "https://api.minimaxi.com",
        "fields": ["apiKey", "baseUrl"],
        "hint": "国内密钥配 api.minimaxi.com，国际密钥配 api.minimax.io，两边不能混用。密钥先存在这里，模型接入后直接使用。",
        "series": [
            {"id": "image", "name": "Image", "kind": "image"},
            {"id": "hailuo", "name": "Hailuo", "kind": "video"},
        ],
    },
    {
        "id": "kling",
        "name": "可灵",
        "envKey": "KLING_API_KEY",
        "defaultBaseUrl": "https://api-beijing.klingai.com",
        "fields": ["apiKey", "baseUrl", "accessKey", "secretKey"],
        "hint": "国内用 api-beijing.klingai.com，海外用 api-singapore.klingai.com。新版控制台填 API Key；旧版开放平台填 Access Key 和 Secret Key。",
        "series": [
            {"id": "kling", "name": "Kling", "kind": "video"},
        ],
    },
]

VIDEO_TASKS = [
    {"id": "text", "label": "文生视频"},
    {"id": "first", "label": "首帧"},
    {"id": "last", "label": "首尾帧"},
    {"id": "omni", "label": "全模态参考"},
    {"id": "edit", "label": "编辑视频"},
    {"id": "extend", "label": "延长视频"},
    {"id": "draft", "label": "样片转正式"},
]


def _image(
    id: str, name: str, *, recommended: bool = False, retiring: bool = False,
    max_refs: int, tiers: list[str], profile: str, pixel_min: int, pixel_max: int,
    output_formats: list[str], default_output: str, optimize: list[str],
    sequential: bool = False, stream: bool = False, web_search: bool = False,
    layer: bool = False, layer_max: bool = False, ocr: bool = False,
    safety: bool = False, backgrounds: list[str] | None = None,
    default_background: str | None = None, rgba: str = "none", note: str = "",
    provider: str = "ark", series: str = "seedream",
) -> dict:
    return {
        "id": id,
        "name": name,
        "kind": "image",
        "provider": provider,
        "series": series,
        "recommended": recommended,
        "retiring": retiring,
        "note": note,
        "tasks": ["text", "edit"] + (["batch"] if sequential else []) + (["layers"] if layer else []),
        "maxRefs": max_refs,
        "tiers": tiers,
        "defaultTier": tiers[0] if "2K" not in tiers else "2K",
        "layerTiers": ["auto", *tiers] if layer else [],
        "profile": profile,
        "pixelMin": pixel_min,
        "pixelMax": pixel_max,
        "outputFormats": output_formats,
        "defaultOutput": default_output,
        "backgrounds": backgrounds or [],
        "defaultBackground": default_background,
        "optimizeModes": optimize,
        "defaultOptimize": "standard",
        "sequential": sequential,
        "stream": stream,
        "webSearch": web_search,
        "layer": layer,
        "layerMax": layer_max,
        "ocr": ocr,
        "safety": safety,
        "rgba": rgba,
        "defaultWatermark": True,
    }


IMAGE_MODELS = [
    _image(
        "doubao-seedream-5-5-261028", "Seedream 5.5", recommended=True,
        max_refs=10, tiers=["1K", "1.5K", "2K"], profile="s55",
        pixel_min=921_600, pixel_max=4_624_220,
        output_formats=["png", "jpeg"], default_output="png", optimize=["standard"],
        layer=True, layer_max=True, ocr=True, safety=True,
        backgrounds=["auto", "transparent", "opaque"], default_background="auto",
        rgba="free", note="默认图片模型。文生图可直接出透明图，支持图层拆分。",
    ),
    _image(
        "doubao-seedream-5-0-pro-260628", "Seedream 5.0 pro",
        max_refs=10, tiers=["1K", "1.5K", "2K"], profile="s55",
        pixel_min=921_600, pixel_max=4_624_220,
        output_formats=["png", "jpeg"], default_output="jpeg",
        optimize=["standard", "fast"], layer=True, safety=True,
        backgrounds=["transparent", "opaque"], default_background="opaque",
        rgba="single-alpha", note="可选快速提示词优化。透明图只接受一张已带透明通道的参考图。",
    ),
    _image(
        "doubao-seedream-5-0-flash-260915", "Seedream 5.0 flash",
        max_refs=10, tiers=["1K", "1.5K", "2K"], profile="s55",
        pixel_min=921_600, pixel_max=4_624_220,
        output_formats=["png", "jpeg"], default_output="jpeg", optimize=["standard"],
        layer=True, safety=True,
        backgrounds=["transparent", "opaque"], default_background="opaque",
        rgba="single-alpha", note="速度更快。透明图只接受一张已带透明通道的参考图。",
    ),
    _image(
        "doubao-seedream-5-0-260128", "Seedream 5.0 lite", retiring=True,
        max_refs=14, tiers=["2K", "3K", "4K"], profile="lite",
        pixel_min=3_686_400, pixel_max=16_777_216,
        output_formats=["png", "jpeg"], default_output="jpeg", optimize=["standard"],
        sequential=True, stream=True, web_search=True,
        note="即将下线。组图、流式输出和联网搜索只在这一档。",
    ),
    _image(
        "doubao-seedream-4-5-251128", "Seedream 4.5", retiring=True,
        max_refs=14, tiers=["2K", "4K"], profile="s45",
        pixel_min=3_686_400, pixel_max=16_777_216,
        output_formats=["jpeg"], default_output="jpeg", optimize=["standard"],
        sequential=True, stream=True, note="即将下线。支持组图和流式输出，只出 JPEG。",
    ),
    _image(
        "doubao-seedream-4-0-250828", "Seedream 4.0", retiring=True,
        max_refs=14, tiers=["1K", "2K", "4K"], profile="s40",
        pixel_min=921_600, pixel_max=16_777_216,
        output_formats=["jpeg"], default_output="jpeg", optimize=["standard", "fast"],
        sequential=True, stream=True, note="即将下线。支持组图、流式输出和快速提示词优化。",
    ),
]


def _video(
    id: str, name: str, *, family: str, recommended: bool = False, retiring: bool = False,
    resolutions: list[str], default_resolution: str, duration_min: int, duration_max: int,
    smart_duration: bool, tasks: list[str], refs: tuple[int, int, int], audio_only: bool,
    generate_audio: bool, output_formats: list[str], lock_ratio: list[str],
    lock_duration: list[str],     seed: bool = False, camera: bool = False, frames: bool = False,
    draft: bool = False, service_tier: bool = False, priority: bool = False,
    web_search: bool = False, hevc1080: bool = False, hevc4k: bool = False,
    text_adaptive: bool = True, note: str = "",
    provider: str = "ark", series: str = "seedance",
) -> dict:
    return {
        "id": id,
        "name": name,
        "kind": "video",
        "provider": provider,
        "series": series,
        "family": family,
        "recommended": recommended,
        "retiring": retiring,
        "note": note,
        "tasks": tasks,
        "resolutions": resolutions,
        "defaultResolution": default_resolution,
        "durationMin": duration_min,
        "durationMax": duration_max,
        "smartDuration": smart_duration,
        "defaultDurationMode": "smart" if smart_duration and family.startswith("2.5") else "omit",
        "maxRefImages": refs[0],
        "maxRefVideos": refs[1],
        "maxRefAudios": refs[2],
        "audioOnly": audio_only,
        "generateAudio": generate_audio,
        "outputFormats": output_formats,
        "defaultOutput": "mp4",
        "lockRatioTasks": lock_ratio,
        "lockDurationTasks": lock_duration,
        "seed": seed,
        "cameraFixed": camera,
        "frames": frames,
        "draft": draft,
        "serviceTier": service_tier,
        "priority": priority,
        "webSearch": web_search,
        "hevc1080": hevc1080,
        "hevc4k": hevc4k,
        "textAdaptive": text_adaptive,
        "defaultRatio": "adaptive" if text_adaptive else "16:9",
        "defaultWatermark": False,
        "defaultGenerateAudio": True,
    }


_V2_TASKS = ["text", "first", "last", "omni", "edit", "extend"]
_LOCK25 = ["first", "last", "edit", "extend"]

VIDEO_MODELS = [
    _video(
        "doubao-seedance-2-5-flash-261115", "Seedance 2.5 flash", family="2.5",
        recommended=True, resolutions=["480p", "720p"], default_resolution="720p",
        duration_min=4, duration_max=30, smart_duration=True, tasks=_V2_TASKS,
        refs=(10, 5, 5), audio_only=True, generate_audio=True, output_formats=["mp4", "mov"],
        lock_ratio=_LOCK25, lock_duration=["edit"], priority=True, web_search=True,
        note="默认视频模型。适合试片，分辨率到 720p，时长 4–30 秒。",
    ),
    _video(
        "doubao-seedance-2-5-260628", "Seedance 2.5", family="2.5",
        resolutions=["480p", "720p", "1080p", "4k"], default_resolution="720p",
        duration_min=4, duration_max=30, smart_duration=True, tasks=_V2_TASKS + ["draft"],
        refs=(30, 10, 10), audio_only=True, generate_audio=True, output_formats=["mp4", "mov"],
        lock_ratio=_LOCK25, lock_duration=["edit"], draft=True, priority=True, web_search=True,
        hevc1080=True, hevc4k=True,
        note="高质量成片。1080p 和 4K 是 10bit H.265。只有这一档能开样片模式。",
    ),
    _video(
        "doubao-seedance-2-0-260128", "Seedance 2.0", family="2.0",
        resolutions=["480p", "720p", "1080p", "4k"], default_resolution="720p",
        duration_min=4, duration_max=15, smart_duration=True, tasks=_V2_TASKS,
        refs=(9, 3, 3), audio_only=False, generate_audio=True, output_formats=["mp4"],
        lock_ratio=[], lock_duration=[], priority=True, web_search=True, hevc4k=True,
        note="时长 4–15 秒。参考素材不能只有音频。4K 为 10bit H.265。",
    ),
    _video(
        "doubao-seedance-2-0-fast-260128", "Seedance 2.0 fast", family="2.0",
        resolutions=["480p", "720p"], default_resolution="720p",
        duration_min=4, duration_max=15, smart_duration=True, tasks=_V2_TASKS,
        refs=(9, 3, 3), audio_only=False, generate_audio=True, output_formats=["mp4"],
        lock_ratio=[], lock_duration=[], priority=True, web_search=True,
        note="更快，分辨率到 720p。",
    ),
    _video(
        "doubao-seedance-2-0-mini-260615", "Seedance 2.0 mini", family="2.0",
        resolutions=["480p", "720p"], default_resolution="720p",
        duration_min=4, duration_max=15, smart_duration=True, tasks=_V2_TASKS,
        refs=(9, 3, 3), audio_only=False, generate_audio=True, output_formats=["mp4"],
        lock_ratio=[], lock_duration=[], priority=True, web_search=True,
        note="更轻的一档，分辨率到 720p。",
    ),
    _video(
        "doubao-seedance-1-0-pro-250528", "Seedance 1.0 pro", family="1.0", retiring=True,
        resolutions=["480p", "720p", "1080p"], default_resolution="1080p",
        duration_min=2, duration_max=12, smart_duration=False,
        tasks=["text", "first", "last"], refs=(0, 0, 0), audio_only=False,
        generate_audio=False, output_formats=["mp4"], lock_ratio=[], lock_duration=[],
        seed=True, camera=True, frames=True, service_tier=True, text_adaptive=False,
        note="即将下线。种子、帧数、固定镜头和离线推理只在 1.0。",
    ),
    _video(
        "doubao-seedance-1-0-pro-fast-251015", "Seedance 1.0 pro fast", family="1.0",
        retiring=True, resolutions=["480p", "720p", "1080p"], default_resolution="1080p",
        duration_min=2, duration_max=12, smart_duration=False,
        tasks=["text", "first"], refs=(0, 0, 0), audio_only=False,
        generate_audio=False, output_formats=["mp4"], lock_ratio=[], lock_duration=[],
        seed=True, camera=True, frames=True, service_tier=True, text_adaptive=False,
        note="即将下线。没有首尾帧。",
    ),
]


def image_model(model_id: str) -> dict | None:
    return next((m for m in IMAGE_MODELS if m["id"] == model_id), None)


def video_model(model_id: str) -> dict | None:
    return next((m for m in VIDEO_MODELS if m["id"] == model_id), None)


def default_image_id() -> str:
    return next(m["id"] for m in IMAGE_MODELS if m["recommended"])


def default_video_id() -> str:
    return next(m["id"] for m in VIDEO_MODELS if m["recommended"])


def public_catalog() -> dict:
    return {
        "ratios": RATIOS,
        "videoRatios": VIDEO_RATIOS,
        "pixels": {
            profile: {
                tier: {ratio: [w, h] for ratio, (w, h) in ratios.items()}
                for tier, ratios in tiers.items()
            }
            for profile, tiers in PIXELS.items()
        },
        "imageTasks": IMAGE_TASKS,
        "videoTasks": VIDEO_TASKS,
        "providers": PROVIDERS,
        "imageModels": IMAGE_MODELS,
        "videoModels": VIDEO_MODELS,
        "defaults": {"image": default_image_id(), "video": default_video_id()},
        "limits": {
            "imageBytes": 30 * 1024 * 1024,
            "audioBytes": 15 * 1024 * 1024,
            "requestBytes": 64 * 1024 * 1024,
            "imageFormats": ["jpeg", "png", "webp", "bmp", "tiff", "gif", "heic", "heif"],
            "audioFormats": ["wav", "mp3"],
            "videoNote": "参考视频只接受公网 URL 或 asset://，方舟读不到本机文件。",
        },
    }
