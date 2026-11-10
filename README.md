# PaperDrop Homebrew tap

中文 / English · **预发布 / pre-release**

PaperDrop 的个人 tap：macOS 与 Linux **Xfce** 的每日壁纸工具，不是 Homebrew/core 官方配方。
This personal tap packages PaperDrop for macOS and Linux **Xfce**; it is not an official Homebrew/core formula.

> **预发布状态 / Pre-release:** 配方使用 PaperDrop 0.3.3 预发布制品；真机桌面与定时验收尚未完成。
> **Pre-release:** the formula targets PaperDrop 0.3.3, an upstream pre-release. macOS/Xfce real-device desktop and schedule acceptance are still outstanding.

## 安装 / Install

```sh
brew install pelikanm400/tap/paperdrop
```

安装只写 Homebrew 前缀，不开 UI、不换壁纸、不写用户配置、不启用定时任务。然后在桌面会话中**另行运行**：
Installation only writes to the Homebrew prefix: no UI, wallpaper change, user config or schedule. Then run **separately**, in your desktop session:

```sh
paperdrop install
```

macOS 安装时自动用 Xcode Command Line Tools 编译并安装 Swift helper，无须手动 build。Linux 不构建 Swift；实际换壁纸仅支持 Xfce，需要系统提供 `xfconf-query` 与可用的 systemd 用户会话。
On macOS, installation compiles and installs the Swift helper using Xcode Command Line Tools; no manual build. Linux does not build Swift; wallpaper application requires Xfce, system-provided `xfconf-query`, and a working systemd user session.

| 命令 / Command | 用途 / Purpose |
| --- | --- |
| `paperdrop update` | 立即换壁纸 / Change wallpaper now |
| `brew upgrade pelikanm400/tap/paperdrop` | 升级软件 / Upgrade the application |
| `paperdrop status` | 查看状态 / Show status |
| `paperdrop ui` | 本地设置页 / Local settings page |

Homebrew 安装的 `paperdrop upgrade` 只提示 brew 命令，不会通过 pip/pipx 自更新。调度使用稳定的 `opt` 路径；普通 `brew upgrade` 后不用重装调度，也不会恢复已暂停的任务。
For Homebrew installs, `paperdrop upgrade` only explains the brew command; it never self-updates through pip/pipx. Schedules use the stable `opt` path, so ordinary `brew upgrade` needs no schedule reinstall and preserves paused state.

## 从 pipx 迁移 / Migrate from pipx

先用**旧命令的绝对路径**运行 `paperdrop uninstall`，只移除旧调度，保留配置与缓存；然后 `pipx uninstall paperdrop`，确认 `command -v paperdrop` 不再指向旧命令，再按上面的 brew 步骤安装。不要用 `brew link --overwrite` 掩盖命令冲突。需要启用定时的设备，首次迁移运行一次新命令的 `paperdrop install`；**原来暂停的设备不要运行 `install` 或 `resume`**，先用 `paperdrop ui` 查看，直到明确决定恢复定时。
Using the **absolute path to the old executable**, run `paperdrop uninstall` first to remove its schedule while keeping configuration/cache; then run `pipx uninstall paperdrop`. Confirm `command -v paperdrop` no longer resolves to the old copy before following the brew steps above. Do not hide conflicts with `brew link --overwrite`. To enable scheduling, run the new `paperdrop install` once. **For a previously paused setup, do not run `install` or `resume`**; inspect with `paperdrop ui` until you explicitly choose to enable scheduling.

卸载前运行 `paperdrop uninstall` 移除调度，再 `brew uninstall paperdrop`；brew 不替你修改用户调度、配置或缓存。
Before removing the package, run `paperdrop uninstall`, then `brew uninstall paperdrop`; brew does not alter user schedules, configuration or cache for you.

## 边界与维护 / Boundaries and maintenance

Python 运行时隔离在 `libexec`，Pillow 从固定源码资源构建，JPEG/PNG/WebP 编解码使用 Homebrew 原生库。CI 检查安装、只读 UI 与卸载，不下载图源、不设置真实桌面、不安装调度；CI 通过不等于 macOS/Xfce 真机验收完成。预发布身份在真机验收前保留。
The Python runtime is isolated in `libexec`; Pillow is built from a pinned source resource with brewed native JPEG/PNG/WebP codecs. CI checks installation, read-only UI and removal, without image feeds, real desktop changes or schedule installation. CI is not macOS/Xfce real-device acceptance; pre-release status remains until that acceptance.

维护者：`python3 scripts/update_formula.py` 默认只预览，`--apply` 才修改本地配方 URL/推导版本/SHA-256，不碰 Pillow/其他依赖、不提交、不推送、不发版。仅匿名 GET 官方 GitHub releases（含 pre-release、排除 draft），校验元数据、SHA256SUMS 与实际下载的 sdist；详见 [维护说明](docs/maintenance.md)。
Maintainers: `python3 scripts/update_formula.py` previews by default; `--apply` changes only the local formula URL/inferred version/SHA-256. It never changes Pillow/other dependencies, commits, pushes or publishes. It anonymously GETs only official GitHub releases (including pre-releases, excluding drafts), verifying metadata, SHA256SUMS and the downloaded sdist. See [maintenance notes](docs/maintenance.md).

AI 作者披露：代码由 AI agents 编写，包括 Hermes/DeepSeek 与 OpenAI Codex/GPT 的项目参与；所有者提出需求并负责验收与发版决策。发布门槛包括独立 agent review 和匿名制品校验，不代表人工逐行审计。代码 MIT；远程壁纸图片权利由各图源决定。
AI authorship: AI agents write the code, with Hermes/DeepSeek and OpenAI Codex/GPT participation in the project. The owner defines requirements and makes acceptance/release decisions. Release gates include independent agent review and anonymous artifact verification, not a claim of line-by-line human audit. Code is MIT; remote wallpaper rights remain with their respective sources.
