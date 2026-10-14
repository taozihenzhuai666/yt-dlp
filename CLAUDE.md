# 本 fork 的工作约定

这是 yt-dlp 官方仓库的 fork（`taozihenzhuai666/yt-dlp`，公开仓库），在它的基础上开发「自动剪辑」工作流。

- 背景、需求、方案和下一步都在 `auto_edit/开发进度.md`，开始工作前先读它。
- 分支：`master` 只用来跟官方同步（`git pull upstream master`）；自动剪辑的开发都在 `auto-edit` 分支。
- 自动剪辑的代码放在 `auto_edit/` 目录，不改 yt-dlp 本身的代码。
- 成品是**竖屏 9:16（1080×1920）**。
- 每完成一步，就更新 `auto_edit/开发进度.md`，然后 commit 并 push 到 `origin auto-edit`。
- 下载的视频放 `downloads/`（已被 `.gitignore` 排除），不要提交视频文件和密钥。
- ffmpeg 来自 Python 包 `imageio-ffmpeg`，不在系统路径里，路径用 `python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"` 获取。
- 参考视频：`downloads/秋芝2046_一站式创作Agent.mp4`。
