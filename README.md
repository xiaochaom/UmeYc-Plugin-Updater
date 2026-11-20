# UmeYc-Plugin-Updater

[English](README.en.md) · 简体中文

Steam Deck 游戏模式的 Decky 插件更新助手。把已安装的插件与它的 GitHub 仓库关联后，即可手动或每日检查更新，也能用手机传送 ZIP 下载地址。

## 使用

1. 在 Decky 打开 `UmeYc-Plugin-Updater`，选择 **添加监听插件**，再选一个尚未监听的已安装插件。若插件清单声明了 GitHub 仓库，地址会自动填入，也可以修改；否则可手动输入公开的 GitHub 仓库或 Releases 地址，或让同一 Wi-Fi 下的手机扫码发送。核对后在 Deck 上点 **保存**。
2. 点 **手动检查**，或打开 **每日检查**。Decky 的后端运行时每 24 小时检查一次；Deck 休眠或关机期间不会检查，也不会自动安装。手动、单插件和每日检查发现可安装的更新时，都会发一条 Decky 通知。每个插件只提醒一次；安装到已提醒的版本或更高版本后，再查到可安装的新版才会再次提醒。重启不会清除去重记录。
3. 监听列表每个插件占一行，有可安装的更新时右上角显示绿点。点插件名打开详情，可单独 **检查更新**、编辑来源或移除监听。有更新时可在详情查看版本及发布说明，再点 **更新** 下载并验证 ZIP。下载连接中断或超时时会自动重试一次；验证通过后还需要在 Decky 的原生弹窗确认安装。
4. **扫码安装插件**：扫码后在手机粘贴公开 HTTPS 的 ZIP 成品地址。回到 Deck，下载并检查 ZIP，核对插件名和版本后再安装。也可直接在 Deck 输入链接。手机不会触发下载或安装。

扫码只在打开对应弹窗时启动局域网输入页；链接一次有效、5 分钟过期。请只在可信的 Wi-Fi 和设备上扫码，避免发送带鉴权令牌的链接。结构校验和哈希校验不意味着插件代码可信，只安装你信任的发布者。通过 Decky 安装可能替换现有同名插件，请按目标插件文档备份重要设置。

插件默认跟随 Steam 界面语言：中文显示简体中文，其他语言显示英文。也可在首页 **界面语言 / Language** 手动选择，或切回 **跟随系统**。插件弹窗、扫码页和更新通知使用当前语言；GitHub 发布说明保留原文，Decky 原生安装确认使用 Steam 界面语言。

## 为什么不用安装时间

Decky 安装的是解包结果，不保证保留原始 ZIP 或它的生成时间。ZIP 内的日期是文件条目的时间；目录时间也会随重装、恢复或手动改动变化。GitHub 的 `published_at` 只描述发布时刻：今天重装上个月的旧版，安装时间仍会晚于新版的发布日期。因此两个时间不能证明哪个版本更新。

- 读取本地 `package.json` 的 `version`，与 GitHub 最新公开正式 Release 的标签按 SemVer 比较（接受 `v` 前缀）。不支持猜测日期版、未知版本、同版本重新打包或把预发行版当正式版。
- 仅检查 Release 上传的 ZIP 成品，不使用 GitHub 自动生成的 **Source code (zip)**。有多个 ZIP 时优先匹配 `<插件名>.zip`，无法唯一选择就不自动选。
- 更新执行前校验 ZIP：必须是单插件 Decky 成品，插件名要与本地一致，`package.json` 版本要匹配 Release 标签且比本地新。若 GitHub 提供 SHA-256，也校验其摘要。版本、标签或成品不规范时不猜测；可核对发布者后使用扫码安装。
- Decky 安装完成后重新读取本地版本，不会把“弹出安装确认”误报为安装成功。

本版本支持公开 GitHub 仓库、公开 HTTPS 下载链接（含 HTTPS 重定向），ZIP 上限 128 MiB、解包上限 512 MiB。安装使用 Decky Loader 自身的安装入口（不是 Decky 插件 SDK 的公开接口），如果 Loader 版本变更导致不可用，更新 Loader 后重试。ZIP 临时文件约 30 分钟后清理，打开确认弹窗后请及时操作。

## 构建和安装

需要 Node.js 20+、pnpm 10 和 Python 3.9+。

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm package
```

用户可从 [GitHub Releases](https://github.com/xiaochaom/UmeYc-Plugin-Updater/releases/latest) 下载 `UmeYc-Plugin-Updater.zip`，在 Decky 的开发者设置使用 **从 ZIP 安装插件**，也可复制 ZIP 成品链接，使用 **从 URL 安装插件**。自行构建的安装包位于 `out/UmeYc-Plugin-Updater.zip`。发布时，Release 标签应与 `package.json` 一致；上传编译后的 ZIP，不要上传 GitHub 自动生成的源码包。

界面与局域网扫码交互参考 [UmeYc-Portal](https://github.com/xiaochaom/UmeYc-Portal)。
