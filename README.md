# LocalTV

跑在你自己电脑上的创作页。浏览器里选模型、填参数，用你自己的火山方舟 API Key 调用 Seedream 生图、Seedance 生视频。计算在方舟完成，提示词、参考图和成片留在本机。

没有 LocalTV 账号，页面也不做登录。费用走你的方舟账户，每次生成都会扣额度。

当前版本 `0.1.0`。能直接生成的只有火山方舟。MiniMax 和可灵可以先把密钥存下来，模型还没接入，页面上会标「即将接入」。

更细的操作见 [使用文档](docs/使用文档.md)。

## 你能做什么

- 文生图、图生图、图层拆分。组图目前只有即将下线的 Seedream 5.0 lite 可选。
- 文生视频、首帧、首尾帧、全模态参考、编辑、延长。样片模式只有 Seedance 2.5 标准版可以开。
- 模型公开的参数都列在页面上。和官方默认值一样的字段不会发送，你改过的才会提交。不支持的字段留在页面上，但是禁用。
- 右上角点项目名即可切换当前项目。左侧「项目」用来浏览成片和新建项目。

参考图可以选本机 png、jpeg，单张不超过 30MB。参考视频必须填公网地址，方舟读不到你电脑上的文件。

## 环境

- Python 3.10 或更高
- 能访问火山方舟的网络
- 一个浏览器

页面默认只监听本机：http://127.0.0.1:8787 。不要把 `LOCALTV_HOST` 改成 `0.0.0.0` 后再暴露到公网。密钥和成片都在这台电脑上。

「选择文件夹」「打开图片」「打开视频」「在访达中显示」是 macOS 上的行为：图片用预览打开，视频用 QuickTime 打开。其他系统请到成片目录里自己打开文件，存储位置在设置里填写绝对路径。

## 启动

在项目目录执行：

```bash
./start.sh
```

Windows 双击 `start.bat`，或在项目目录执行它。第一次会创建 `.venv` 并安装依赖，之后再运行就是直接启动。macOS 上脚本会打开浏览器。关掉这个窗口，页面就停。不想自动打开浏览器时：

```bash
LOCALTV_NO_OPEN=1 ./start.sh
```

也可以自己装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m localtv
```

Windows 激活虚拟环境用 `.venv\Scripts\activate`。换端口：

```bash
LOCALTV_PORT=8799 python -m localtv
```

## 第一次使用

1. 在[火山方舟控制台](https://console.volcengine.com/ark)创建 API Key，并确认要用的 Seedream、Seedance 模型已经开通。
2. 打开页面，点右上角「设置」，在「火山方舟」里粘贴 Key。
3. 接口保持默认：`https://ark.cn-beijing.volces.com/api/v3`。只填到 `/api/v3`，不要填具体的图片或视频接口。
4. 保存。页面上只会显示密钥末尾四位。
5. 回到「图片」或「视频」，写提示词，点生成。没有 Key 时，生成按钮不可用。

密钥写在 `~/.localtv/config.toml`，文件权限是 `0600`（只有当前用户可读写）。不要把这个文件提交到 git，也不要贴到 Issue 里。留空再保存不会清掉已经存好的 Key。要清除某一家的密钥，用设置里对应的清除按钮。

环境变量会盖过文件里的对应密钥：

| 服务商 | 环境变量 | 默认接口 | 现在能不能生成 |
| --- | --- | --- | --- |
| 火山方舟 | `ARK_API_KEY` | `https://ark.cn-beijing.volces.com/api/v3` | 可以 |
| MiniMax | `MINIMAX_API_KEY` | `https://api.minimaxi.com`（国际密钥用 `https://api.minimax.io`） | 还不能，只保存密钥 |
| 可灵 | `KLING_API_KEY` | `https://api-beijing.klingai.com`（海外用 `https://api-singapore.klingai.com`） | 还不能，只保存密钥 |

可灵新版控制台填 API Key；旧版开放平台填 Access Key 和 Secret Key。

## 页面

左侧是「项目」「图片」「视频」。中间上面是画布，结果出现在这里；下面是生成器。右侧是参数。生成器底部可以展开「查看这次实际提交的字段」。

`⌘/Ctrl + Enter` 触发生成。「新对话」只清空当前这一侧的提示词、参考素材和画布，模型和参数留着，已经生成的文件还在项目里。

图片默认模型是 Seedream 5.5，水印默认开启，成片右下角会有「AI 生成」。视频默认模型是 Seedance 2.5 flash，分辨率到 720p，时长 4–30 秒，水印默认关闭，声音默认生成。视频是异步的，提交后不要关掉运行 LocalTV 的终端，完成后会自动下载到当前项目。

灰色的任务或参数是当前模型不支持的，旁边有原因。即将下线的模型名称上会标明。

## 成片放在哪

默认目录是文稿里的 `LocalTV`，也就是 `~/Documents/LocalTV/`。设置里可以改。改的时候，已有项目会一起搬过去。密钥仍留在配置文件里，不会跟着成片走。

```text
~/Documents/LocalTV/
  default/
    project.json
    inputs/              这次任务用过的参考图
    jobs/                每条任务一条记录
    outputs/<任务 id>/   图片或 video.mp4
```

页面上的路径在文稿目录下时会显示成「文稿/…」。

| 变量 | 作用 |
| --- | --- |
| `LOCALTV_HOST` | 监听地址，默认 `127.0.0.1` |
| `LOCALTV_PORT` | 端口，默认 `8787` |
| `LOCALTV_HOME` | 配置目录，默认 `~/.localtv` |
| `LOCALTV_LIBRARY` | 成片目录。设了之后，设置里不能再改存储位置 |
| `LOCALTV_NO_OPEN` | 设为 `1` 时，macOS 启动脚本不打开浏览器 |

`LOCALTV_LIBRARY` 只改变读取位置，不会自动搬家。要从设置里保存新位置，已有项目才会搬过去。

## 仓库里有什么

```text
start.sh / start.bat     创建虚拟环境、安装依赖、启动
localtv/__main__.py      入口
localtv/server.py        本机 HTTP 接口
localtv/catalog.py       模型、任务和参数
localtv/payload.py       按官方默认值决定哪些字段要发送
localtv/ark.py           调用火山方舟
localtv/store.py         配置、项目和成片
localtv/web/             页面
docs/使用文档.md          完整操作说明
```

依赖只有 FastAPI 和 uvicorn，列在 `requirements.txt`。
