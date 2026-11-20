# UmeYc-Plugin-Updater

English · [简体中文](README.md)

A Decky plugin updater for Steam Deck Gaming Mode. Link installed plugins to their GitHub repositories, get notified when updates are ready, or send a ZIP download URL from your phone.

## Use

1. Open **UmeYc-Plugin-Updater** in Decky, choose **Watch a plugin**, and select an installed plugin you aren't already watching. The updater prefills the GitHub repository URL if the plugin declares one, and you can edit it. Otherwise, enter a public GitHub repository or Releases URL, or scan a QR code to send it from a phone on the same Wi-Fi network. Review the URL and select **Save** on the Deck.
2. Select **Check all**, check one plugin from its details, or turn on **Daily checks**. Daily checks run every 24 hours while Decky is running, not while the Deck is asleep or off. All three check methods send a Decky notification for an installable update. A watched plugin won't notify you again until you install the version it notified you about (or a newer one) and a subsequent check finds another installable version. Restarting doesn't clear the notification history.
3. Each watched plugin occupies one row, with a green dot when an update is ready. Select its name to open details, check for updates, edit the source, or stop watching. Select **Update** to download and verify the ZIP, then approve the install in Decky's confirmation dialog. A timeout or interrupted connection is retried once.
4. With **Install via QR code**, scan the code and send the public HTTPS URL of a Decky ZIP, or enter it on the Deck. Review the plugin name and version before proceeding. Scanning the QR code does not download or install anything on its own.

If downloading or verifying a ZIP fails, the dialog shows the reason and Decky sends a notification. You can retry from the same dialog.

By default the plugin follows Steam's interface language: it uses Simplified Chinese for Chinese and English for other languages. Choose **Language / 界面语言** on the home screen to select a language manually or switch back to **System default**. The current language applies to plugin dialogs, the phone form, and update notifications. GitHub release notes remain in their original language. Decky's own install dialog follows Steam's interface language.

The phone form is available only while its dialog is open. QR links expire after five minutes and can be submitted once. Use a trusted network and phone, avoid URLs with authentication tokens, and install only from publishers you trust. ZIP and hash validation do not establish trust in plugin code. Decky may replace an existing plugin of the same name, so follow the publisher's backup guidance.

## How updates are detected

Decky installs extracted files and may not keep the ZIP or its creation time. Local timestamps can change when you reinstall an older plugin or restore a backup, so comparing dates cannot determine which version is newer.

- The updater compares the `version` in the installed plugin's `package.json` against the latest public stable GitHub Release tag using SemVer (with or without a `v` prefix). It doesn't guess at unknown versions, date-based versions, or repackages of the same version.
- It only considers uploaded ZIP assets, not GitHub's automatically generated **Source code (zip)**. If multiple assets exist, it prefers an exact `<plugin name>.zip` match and otherwise requires an unambiguous choice.
- To prepare an update, it verifies the ZIP structure, plugin name, version and GitHub-published SHA-256 when available. It rereads the installed version after Decky finishes, rather than treating the confirmation prompt as a successful install.
- Only public HTTPS download URLs are supported. A ZIP may be up to 128 MiB and up to 512 MiB when extracted. Staged ZIPs expire after about 30 minutes. The updater uses Decky Loader's native install flow, which may require a compatible Loader version.

## Build and install

Requires Node.js 20+, pnpm 10, and Python 3.9+.

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm package
```

Download `UmeYc-Plugin-Updater.zip` from [GitHub Releases](https://github.com/xiaochaom/UmeYc-Plugin-Updater/releases/latest) and use Decky's developer option to install from ZIP, or copy the ZIP asset URL and install from URL. If you build the package yourself, use `out/UmeYc-Plugin-Updater.zip`. To publish, push an annotated tag matching the version in `package.json` (for example, `v0.1.8`). GitHub Actions uses the tag annotation as release notes and uploads the built ZIP and checksum after the tests pass.

The interface and LAN QR flow were inspired by [UmeYc-Portal](https://github.com/xiaochaom/UmeYc-Portal).
