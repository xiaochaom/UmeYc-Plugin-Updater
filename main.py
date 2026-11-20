import asyncio
from contextlib import suppress
from http.client import HTTPException
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from downloads import download_zip, https_url, inspect_zip, manifest_field, read_manifest
from github_auth import GitHubAuth, configured_client_id
from messages import localized, message
from phone_input import PhoneInput, lan_address
from releases import latest_release, release_status, repository_from_url, repository_hint, version_key


CHECK_INTERVAL = 24 * 60 * 60
ZIP_RETENTION = 30 * 60
ANONYMOUS_LIMIT = 60
ANONYMOUS_WINDOW = 60 * 60
MAX_WATCHES = 200


def anonymous_retry_at(quota, now):
    if not quota:
        return 0
    until = max(quota.get("retry_at", 0), quota["reset_at"] if quota["remaining"] == 0 else 0)
    return until if until > now else 0


def installed_plugins(root):
    result = []
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            plugin = read_manifest(folder / "plugin.json")
            name = manifest_field(plugin, "name")
        except (OSError, ValueError):
            continue
        package = {}
        try:
            package = read_manifest(folder / "package.json")
            version = manifest_field(package, "version")
        except (OSError, ValueError):
            version = ""
        repository = repository_hint(package.get("repository")) or repository_hint(plugin.get("repository"))
        result.append({"name": name, "folder": folder.name, "version": version, "repository": repository})
    return result


def install_type(candidate, plugins, root, expected_name=None, expected_tag=None):
    matches = [plugin for plugin in plugins if plugin["name"] == candidate["name"]]
    existing = matches[0] if len(matches) == 1 else None
    if len(matches) > 1:
        raise ValueError(message("本地有多个同名插件，无法安全安装", "Multiple installed plugins share this name."))
    folder = root / candidate["folder"]
    if (folder.exists() or folder.is_symlink()) and (not existing or existing["folder"] != candidate["folder"]):
        raise ValueError(message("ZIP 的目录名与其他本地插件冲突", "The ZIP folder conflicts with another installed plugin."))
    target = version_key(candidate["version"])
    current = version_key(existing["version"]) if existing else None
    if expected_name is not None:
        if candidate["name"] != expected_name:
            raise ValueError(message("ZIP 内的插件名与监听的插件不一致", "The plugin name in the ZIP does not match the watch."))
        if target is None or target != version_key(expected_tag):
            raise ValueError(message("ZIP 内的版本与 GitHub Release 标签不一致", "The version inside the ZIP does not match the release tag."))
        if not current or target <= current:
            raise ValueError(message("本地插件已变化，或成品版本并不比本地更新；请重新检查",
                                     "The installed plugin changed or the ZIP is not newer. Check again."))
    if not existing:
        return 0
    if target is None or current is None:
        return 4
    return 2 if target > current else 3 if target < current else 1


def should_notify(version, release, notified_tag):
    if release_status(version, release) != "update":
        return False
    notified_version = version_key(notified_tag)
    return notified_version is None or version_key(version) >= notified_version


class Plugin:
    def __init__(self):
        self.plugin_dir = Path(os.environ["DECKY_PLUGIN_DIR"]).parent
        self.settings_path = Path(os.environ["DECKY_PLUGIN_SETTINGS_DIR"]) / "updater.json"
        self.github = GitHubAuth(self.settings_path.with_name("github-session.json"), configured_client_id())
        self.staging = Path(os.environ["DECKY_PLUGIN_RUNTIME_DIR"]) / "staged-zips"
        self.settings = {"daily": False, "last_checked": 0, "watches": {}, "check_queue": None,
                         "check_manual": False, "anonymous_quota": None}
        if self.settings_path.exists():
            self.settings.update(read_manifest(self.settings_path, limit=32 * 1024**2))
        self.check_lock = asyncio.Lock()
        self.download_lock = asyncio.Lock()
        self.phone_lock = asyncio.Lock()
        self.phone = None
        self.scheduler = None
        self.wake = asyncio.Event()

    async def _main(self):
        self.scheduler = asyncio.create_task(self._daily_loop())

    async def _unload(self):
        if self.scheduler:
            self.scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await self.scheduler
        async with self.phone_lock:
            if self.phone:
                await asyncio.to_thread(self.phone.close)
                self.phone = None

    def _save(self, **changes):
        updated = {**self.settings, **changes}
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.settings_path)
        self.settings = updated

    async def _daily_loop(self):
        import decky

        while True:
            self.wake.clear()
            self._clean_staging()
            if self._scheduled_check_due():
                with suppress(OSError):
                    await self._check(True)
                    await decky.emit("updates_changed")
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    def _anonymous_retry_at(self):
        return anonymous_retry_at(self.settings["anonymous_quota"], time.time())

    def _scheduled_check_due(self):
        if not self.settings["watches"] or (self._anonymous_retry_at() and not self.github.token()):
            return False
        if self.settings["check_queue"] is not None:
            return self.settings["check_manual"] or self.settings["daily"]
        return self.settings["daily"] and time.time() - self.settings["last_checked"] >= CHECK_INTERVAL

    async def state(self):
        plugins = installed_plugins(self.plugin_dir)
        installed = {plugin["name"]: plugin["version"] for plugin in plugins}
        watches = []
        for name, source in self.settings["watches"].items():
            release = source.get("release")
            version = installed.get(name)
            watches.append({"name": name, "repo": source["repo"], "version": version,
                            "status": release_status(version, release), "release": release})
        github = self.github.status()
        return {"daily": self.settings["daily"], "last_checked": self.settings["last_checked"],
                "installed": plugins, "watches": watches, "github": github,
                "check_pending": len(self.settings["check_queue"] or []),
                "check_retry_at": 0 if github["connected"] else self._anonymous_retry_at(),
                "check_auto_resume": self.settings["check_manual"] or self.settings["daily"]}

    async def start_github_login(self):
        return await self.github.start()

    async def poll_github_login(self, session_id):
        result = await self.github.poll(session_id)
        if result["status"] == "connected":
            self.wake.set()
        return result

    async def cancel_github_login(self, session_id):
        self.github.cancel(session_id)

    async def sign_out_github(self):
        try:
            self.github.sign_out()
        except OSError:
            return {"status": "error"}
        return {"status": "signed_out"}

    async def set_daily(self, enabled):
        self._save(daily=enabled is True)
        self.wake.set()
        return await self.state()

    @localized
    async def watch(self, name, url, language="zh"):
        repo = repository_from_url(url)
        if name not in {plugin["name"] for plugin in installed_plugins(self.plugin_dir)}:
            raise ValueError(message("请选择已安装插件", "Select an installed plugin."))
        watches = self.settings["watches"]
        if name not in watches and len(watches) >= MAX_WATCHES:
            raise ValueError(message(f"最多监听 {MAX_WATCHES} 个插件", f"You can watch up to {MAX_WATCHES} plugins."))
        if watches.get(name, {}).get("repo") != repo:
            queue = self.settings["check_queue"]
            self._save(watches={**watches, name: {"repo": repo}},
                       check_queue=[*queue, name] if queue is not None and name not in queue else queue)
        self.wake.set()
        return await self.state()

    async def unwatch(self, name):
        watches = {key: value for key, value in self.settings["watches"].items() if key != name}
        queue = self.settings["check_queue"]
        pending = [target for target in queue if target != name] if queue is not None else None
        changes = {"watches": watches, "check_queue": pending or None}
        if pending == []:
            changes.update(last_checked=time.time() if watches else 0, check_manual=False)
        self._save(**changes)
        return await self.state()

    async def check(self):
        checked = await self._check(False)
        return {**await self.state(), "checked_names": checked}

    @localized
    async def check_plugin(self, name, language="zh"):
        if not isinstance(name, str):
            raise ValueError(message("请选择要检查的监听插件", "Select a watched plugin to check."))
        checked = await self._check(False, name)
        return {**await self.state(), "checked_names": checked}

    async def _check(self, daily, name=None):
        async with self.check_lock:
            if daily and not self._scheduled_check_due():
                return []
            sources = self.settings["watches"]
            queue = self.settings["check_queue"]
            if name is not None:
                if name not in sources:
                    raise ValueError(message("此插件已不在监听列表中", "This plugin is no longer watched."))
                targets = {name: sources[name]}
            else:
                targets = {target: sources[target] for target in (sources if queue is None else queue) if target in sources}
            if not sources:
                return []
            results = {}
            token = self.github.token()
            quota = self.settings["anonymous_quota"]
            if not token and targets:
                if not quota or quota["reset_at"] <= time.time():
                    quota = {"remaining": ANONYMOUS_LIMIT, "reset_at": time.time() + ANONYMOUS_WINDOW,
                             "retry_at": (quota or {}).get("retry_at", 0)}
                else:
                    quota = dict(quota)
            for target, source in targets.items():
                repo = source["repo"]
                rate_limit = {}
                if not token:
                    if not quota["remaining"] or anonymous_retry_at(quota, time.time()):
                        break
                    quota["remaining"] -= 1
                try:
                    if token:
                        release = await asyncio.to_thread(latest_release, repo, target, token=token)
                    else:
                        release = await asyncio.to_thread(latest_release, repo, target, rate_limit=rate_limit)
                except (TimeoutError, socket.timeout):
                    release = {"error": "releaseTimeout"}
                except ssl.SSLError:
                    release = {"error": "releaseTlsError"}
                except (OSError, HTTPException, ValueError, KeyError, TypeError):
                    release = {"error": "releaseNetworkError"}
                if not token:
                    remaining = rate_limit.get("remaining")
                    reset_at = rate_limit.get("reset_at")
                    if remaining is not None:
                        quota["remaining"] = min(quota["remaining"], remaining)
                    if reset_at and reset_at >= time.time():
                        quota["reset_at"] = reset_at + 1
                    if release.get("error") == "releaseRateLimit":
                        retry_after = rate_limit.get("retry_after")
                        if retry_after is not None or remaining != 0:
                            quota["retry_at"] = time.time() + max(1, retry_after if retry_after is not None else 60)
                        break
                results[target] = {**source, "release": release}
            watches = self.settings["watches"]
            retained = {target: result for target, result in results.items() if watches.get(target) is targets[target]}
            if retained:
                installed = {plugin["name"]: plugin["version"] for plugin in installed_plugins(self.plugin_dir)}
                for target, result in retained.items():
                    result["notification_pending"] = should_notify(installed.get(target), result["release"], result.get("notified_tag"))
            changes = {"watches": {**watches, **retained}, "anonymous_quota": quota}
            if name is None:
                pending = [target for target in watches if target not in retained
                           and (target in targets or watches[target] is not sources.get(target))]
                changes.update(check_queue=pending or None,
                               check_manual=bool(pending) and (not daily or self.settings["check_manual"]))
                if not pending:
                    changes["last_checked"] = time.time()
            self._save(**changes)
            return list(retained)

    async def take_notifications(self):
        async with self.check_lock:
            watches = self.settings["watches"]
            if not any(source.get("notification_pending") for source in watches.values()):
                return []
            installed = {plugin["name"]: plugin["version"] for plugin in installed_plugins(self.plugin_dir)}
            updated = dict(watches)
            notifications = []
            for name, source in watches.items():
                if not source.get("notification_pending"):
                    continue
                updated[name] = {**source, "notification_pending": False}
                release = source.get("release")
                if should_notify(installed.get(name), release, source.get("notified_tag")):
                    updated[name]["notified_tag"] = release["tag"]
                    notifications.append({"name": name, "tag": release["tag"]})
            self._save(watches=updated)
            return notifications

    @localized
    async def start_phone(self, mode, language="zh"):
        validators = {"repository": repository_from_url, "zip": https_url}
        if mode not in validators:
            raise ValueError(message("不支持的扫码模式", "Unsupported QR input mode."))
        async with self.phone_lock:
            if self.phone:
                await asyncio.to_thread(self.phone.close)
                self.phone = None
            self.phone = PhoneInput(lan_address(), mode, validators[mode], language=language)
            return {"id": self.phone.token, "url": self.phone.url}

    async def poll_phone(self, token):
        if not self.phone or self.phone.token != token:
            return {"status": "expired"}
        return self.phone.status()

    async def stop_phone(self, token):
        async with self.phone_lock:
            if self.phone and self.phone.token == token:
                await asyncio.to_thread(self.phone.close)
                self.phone = None

    def _clean_staging(self):
        for archive in self.staging.glob("*.zip"):
            with suppress(OSError):
                if time.time() - archive.stat().st_mtime > ZIP_RETENTION:
                    archive.unlink()

    @localized
    async def prepare_install(self, url, language="zh"):
        return await self._prepare(url)

    @localized
    async def prepare_update(self, name, tag, url, language="zh"):
        source = self.settings["watches"].get(name, {})
        release = source.get("release") or {}
        asset = release.get("asset") or {}
        if release.get("tag") != tag or not asset or asset["url"] != url:
            return {"error": message("更新信息已失效，请重新查看", "The update details changed. Check for updates again.")}
        return await self._prepare(asset["url"], asset.get("digest"), name, tag)

    async def _prepare(self, url, digest=None, name=None, tag=None):
        if self.download_lock.locked():
            return {"error": message("已有 ZIP 在下载，请稍后再试", "A ZIP is already downloading. Try again shortly.")}
        async with self.download_lock:
            try:
                candidate = await asyncio.to_thread(self._stage_zip, url, digest, name, tag)
            except ValueError as error:
                return {"error": str(error)}
            return {"candidate": candidate}

    def _stage_zip(self, url, digest, name, tag):
        self._clean_staging()
        self.staging.mkdir(mode=0o700, parents=True, exist_ok=True)
        archive = self.staging / f"{secrets.token_hex(16)}.zip"
        try:
            checksum = download_zip(url, archive, digest)
            candidate = inspect_zip(archive)
            kind = install_type(candidate, installed_plugins(self.plugin_dir), self.plugin_dir, name, tag)
            return {**candidate, "artifact": f"file://{archive}", "sha256": checksum, "kind": kind}
        except BaseException:
            with suppress(OSError):
                archive.unlink(missing_ok=True)
            raise
