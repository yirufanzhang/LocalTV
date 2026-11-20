# LocalTV

本机创作页。用你自己的火山方舟 API Key 调用 Seedream 和 Seedance，参数在页面上配置，成片留在本机。

```bash
./start.sh
```

Windows 双击 `start.bat`，或在项目目录执行它。第一次会自己建虚拟环境并安装依赖，之后再运行就是直接打开。浏览器访问 http://127.0.0.1:8787 ，在设置里保存 API Key。macOS 上脚本会替你打开这个地址。

使用说明见 [docs/使用文档.md](docs/使用文档.md)。

密钥按服务商写在 `~/.localtv/config.toml`，只有当前用户可读写。火山方舟、MiniMax、可灵各自保存接口地址和密钥。环境变量 `ARK_API_KEY`、`MINIMAX_API_KEY`、`KLING_API_KEY` 会盖过对应服务商的文件密钥。成片默认在文稿的 `LocalTV` 文件夹，也就是 `~/Documents/LocalTV/`，可以在设置里修改。`LOCALTV_LIBRARY` 会盖过页面上的存储位置。当前能直接生成的是火山方舟的 Seedream 和 Seedance。参考视频只能填公网地址，方舟读不到本机文件。
