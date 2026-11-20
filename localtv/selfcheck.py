"""不联网，检查参数怎么收成方舟请求。"""

from __future__ import annotations

from localtv.catalog import default_image_id, default_video_id
from localtv.payload import build

IMAGE = default_image_id()
VIDEO = default_video_id()


def check(name: str, built, *, contains: dict | None = None, absent: list[str] | None = None, error_has: str | None = None) -> None:
    if error_has:
        blob = " ".join(built.errors)
        if error_has not in blob:
            raise SystemExit(f"{name}: 期望错误包含「{error_has}」，实际 {built.errors}")
        print(f"ok  {name}")
        return
    if built.errors:
        raise SystemExit(f"{name}: 不该失败 {built.errors}")
    for key, value in (contains or {}).items():
        if built.payload.get(key) != value:
            raise SystemExit(f"{name}: {key} = {built.payload.get(key)!r}，期望 {value!r}\n{built.payload}")
    for key in absent or []:
        if key in built.payload:
            raise SystemExit(f"{name}: 不该提交 {key}")
    print(f"ok  {name}")


def main() -> None:
    plain = build("image", {"model": IMAGE, "task": "text", "prompt": "雨后的城市"})
    check("默认文生图不带尺寸和水印", plain, contains={"model": IMAGE, "prompt": "雨后的城市"}, absent=["size", "watermark", "image"])

    guided = build("image", {
        "model": IMAGE, "task": "text", "prompt": "按这张图改成夜景",
        "images": ["https://example.com/ref.png"],
    })
    check("文生图可以带参考图", guided, contains={"image": "https://example.com/ref.png"})

    wide = build("image", {
        "model": IMAGE, "task": "text", "prompt": "夜景",
        "sizeMode": "ratio", "tier": "2K", "ratio": "16:9",
    })
    check("16:9 换成像素", wide, contains={"size": "2816x1584"})

    tiny = build("image", {
        "model": IMAGE, "task": "text", "prompt": "小图",
        "sizeMode": "custom", "width": 512, "height": 512,
    })
    check("像素过小", tiny, error_has="总像素")

    alpha = build("image", {
        "model": IMAGE, "task": "text", "prompt": "图标",
        "outputFormat": "jpeg", "background": "transparent",
    })
    check("JPEG 不能透明", alpha, error_has="JPEG")

    off = build("image", {"model": IMAGE, "task": "text", "prompt": "无水印", "watermark": False})
    check("关掉水印会提交", off, contains={"watermark": False})

    layers = build("image", {"model": IMAGE, "task": "layers", "prompt": "", "images": []})
    check("拆分缺图", layers, error_has="一张")

    lite = build("image", {
        "model": "doubao-seedream-5-0-260128", "task": "batch", "prompt": "一组海报",
        "maxImages": 4,
    })
    check("组图", lite, contains={"sequential_image_generation": "auto", "sequential_image_generation_options": {"max_images": 4}})

    no_batch = build("image", {"model": IMAGE, "task": "batch", "prompt": "不行"})
    check("5.5 没有组图", no_batch, error_has="不能做")

    video = build("video", {"model": VIDEO, "task": "text", "prompt": "狐狸回头", "durationMode": "smart"})
    check("默认视频省略时长和分辨率", video, contains={"model": VIDEO}, absent=["duration", "resolution", "generate_audio", "watermark"])

    referenced = build("video", {
        "model": VIDEO, "task": "text", "prompt": "人物按参考图走路",
        "images": ["https://example.com/ref.png"], "durationMode": "seconds", "duration": 5,
    })
    check("文生视频可以带参考图", referenced, contains={
        "content": [
            {"type": "text", "text": "人物按参考图走路"},
            {"type": "image_url", "image_url": {"url": "https://example.com/ref.png"}, "role": "reference_image"},
        ],
        "duration": 5,
    })

    hd = build("video", {"model": VIDEO, "task": "text", "prompt": "狐狸", "resolution": "1080p"})
    check("flash 没有 1080p", hd, error_has="1080p")

    edit = build("video", {
        "model": "doubao-seedance-2-5-260628", "task": "edit", "prompt": "去掉路人",
        "videos": ["https://example.com/a.mp4"], "ratio": "16:9", "durationMode": "seconds", "duration": 8,
    })
    check("编辑锁定比例和时长", edit, contains={"ratio": "adaptive", "duration": -1, "omni_reference_task_type": "edit"})

    frames = build("video", {
        "model": "doubao-seedance-1-0-pro-250528", "task": "text", "prompt": "花田",
        "durationMode": "frames", "frames": 57, "ratio": "16:9",
    })
    check("合法帧数", frames, contains={"frames": 57})

    bad_frames = build("video", {
        "model": "doubao-seedance-1-0-pro-250528", "task": "text", "prompt": "花田",
        "durationMode": "frames", "frames": 58,
    })
    check("非法帧数", bad_frames, error_has="25 + 4n")

    adaptive = build("video", {
        "model": "doubao-seedance-1-0-pro-250528", "task": "text", "prompt": "花田", "ratio": "adaptive",
    })
    check("1.0 文生视频不能自适应", adaptive, error_has="自适应")

    local_video = build("video", {
        "model": "doubao-seedance-2-5-260628", "task": "omni", "prompt": "参考",
        "videos": ["data-local:video/mp4;bytes=10"],
    })
    check("本地视频被拒绝", local_video, error_has="公网")

    print("selfcheck passed")


if __name__ == "__main__":
    main()
