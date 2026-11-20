from asyncio import gather
from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPConnection
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import ssl
import stat
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase, mock
from urllib.parse import urlencode
from zipfile import ZipFile, ZipInfo

from downloads import PublicHTTPSConnection, download_zip, https_url, inspect_zip
from main import Plugin, install_type, installed_plugins
from phone_input import PhoneInput
from releases import latest_release, release_status, repository_from_url, version_key


def package_zip(path, name="Test Plugin", version="1.10.0", extra=None, built=True):
    with ZipFile(path, "w") as archive:
        archive.writestr("Test/plugin.json", json.dumps({"name": name, "flags": []}))
        archive.writestr("Test/package.json", json.dumps({"version": version}))
        if built:
            archive.writestr("Test/dist/index.js", "export default () => ({});")
        if extra:
            archive.writestr(extra, "extra")


def asset(name):
    return {"state": "uploaded", "name": name, "browser_download_url": f"https://example.com/{name}"}


def fake_release(assets):
    payload = json.dumps({"draft": False, "prerelease": False, "name": "Test release", "tag_name": "v1.10.0",
                          "body": "Test notes", "published_at": "2026-10-01T00:00:00Z", "assets": assets}).encode()

    @contextmanager
    def response(*_args):
        stream = BytesIO(payload)
        stream.status = 200
        yield stream

    return response


class ReleaseTests(TestCase):
    def test_repository_inputs(self):
        self.assertEqual(repository_from_url(" github.com/Owner/Repo.git "), "owner/repo")
        self.assertEqual(repository_from_url("git@github.com:Owner/Repo.git"), "owner/repo")
        self.assertEqual(repository_from_url("https://github.com/Owner/Repo/releases/tag/v1.0.0"), "owner/repo")
        for value in ("https://evil.example/one/two", "https://github.com@evil.example/one/two",
                      "https://github.com/owner/..", "https://github.com/owner/repo/issues"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository_from_url(value)

    def test_installed_plugins_expose_only_valid_github_repository_hints(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            examples = (
                ({"repository": "git@github.com:Owner/Repo.git", "version": "1.0.0"}, {}, "owner/repo"),
                ({"repository": {"type": "git", "url": "git+https://github.com/Owner/Other.git"}}, {}, "owner/other"),
                ({"repository": "git+ssh://git@github.com/Owner/Ssh.git"}, {}, "owner/ssh"),
                ({}, {"repository": "github:Owner/Fallback"}, "owner/fallback"),
                ({"repository": "https://gitlab.com/owner/repo"}, {}, None),
                ({"repository": "https://github.com@elsewhere.example/owner/repo"}, {}, None),
                ({"repository": {"url": 123}}, {}, None),
                ({}, {}, None),
            )
            for index, (package, manifest, _) in enumerate(examples):
                folder = root / f"plugin-{index}"
                folder.mkdir()
                (folder / "plugin.json").write_text(json.dumps({**manifest, "name": folder.name}))
                (folder / "package.json").write_text(json.dumps(package))

            actual = installed_plugins(root)
            self.assertEqual([item["repository"] for item in actual],
                             [f"https://github.com/{repo}" if repo else None for _, _, repo in examples])
            self.assertEqual([item["version"] for item in actual], ["1.0.0"] + [""] * (len(examples) - 1))

    def test_semver(self):
        self.assertGreater(version_key("v1.10.0"), version_key("1.9.0"))
        self.assertGreater(version_key("1.0.0-zh-cn.25"), version_key("1.0.0-zh-cn.9"))
        self.assertGreater(version_key("1.0.0"), version_key("1.0.0-rc.25"))
        self.assertEqual(version_key("v1.0.0+newbuild"), version_key("1.0.0"))
        self.assertIsNone(version_key("nightly"))

    def test_status_does_not_use_timestamps(self):
        release = {"tag": "v1.10.0", "published_at": "2000-01-01", "asset": asset("Test.zip")}
        self.assertEqual(release_status("1.9.0", release), "update")
        self.assertEqual(release_status("1.10.0", release), "current")
        self.assertEqual(release_status("2.0.0", release), "current")
        self.assertEqual(release_status("dev", release), "unknown")
        self.assertEqual(release_status(None, release), "missing")

    def test_asset_is_selected_only_when_unambiguous(self):
        for assets, expected in (([asset("Test.zip"), asset("Other.zip")], "Test.zip"),
                                 ([asset("Test-v1.10.0.zip")], "Test-v1.10.0.zip"),
                                 ([asset("One.zip"), asset("Two.zip")], None), ([asset("note.txt")], None)):
            with self.subTest(expected=expected), mock.patch("releases.open_https", fake_release(assets)):
                release = latest_release("owner/repo", "Test")
                self.assertEqual((release["asset"] or {}).get("name"), expected)
                self.assertEqual(release["notes"], "Test notes")


class ZipTests(TestCase):
    def test_decky_zip_and_update_validation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "test.zip"
            package_zip(archive)
            candidate = inspect_zip(archive)
            installed = [{"folder": "Test", "name": "Test Plugin", "version": "1.9.0"}]
            self.assertEqual(candidate, {"folder": "Test", "name": "Test Plugin", "version": "1.10.0", "root": False})
            self.assertEqual(install_type(candidate, installed, root, "Test Plugin", "v1.10.0"), 2)
            with self.assertRaisesRegex(ValueError, "插件名"):
                install_type(candidate, installed, root, "Other Plugin", "v1.10.0")
            with self.assertRaisesRegex(ValueError, "标签"):
                install_type(candidate, installed, root, "Test Plugin", "v1.11.0")
            with self.assertRaisesRegex(ValueError, "本地插件"):
                install_type(candidate, [], root, "Test Plugin", "v1.10.0")
            self.assertEqual(install_type({**candidate, "version": "1.0.0"}, installed, root), 3)
            (root / "Test").mkdir()
            with self.assertRaisesRegex(ValueError, "冲突"):
                install_type(candidate, [], root)

    def test_rejects_unbuilt_zip_and_unsafe_archive_layouts(self):
        symlink = ZipInfo("Test/link")
        symlink.create_system = 3
        symlink.external_attr = stat.S_IFLNK << 16
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "test.zip"
            for extra, built in ((None, False), ("Other/plugin.json", True), ("Test/../outside", True),
                                 ("Test/dist/index.js/extra", True), (symlink, True)):
                with self.subTest(extra=extra, built=built), self.assertRaises(ValueError):
                    package_zip(archive, extra=extra, built=built)
                    inspect_zip(archive)

    def test_download_hash(self):
        payload = b"plugin zip bytes"

        @contextmanager
        def response(_url):
            stream = BytesIO(payload)
            stream.status = 200
            stream.getheader = lambda _: str(len(payload))
            yield stream

        with TemporaryDirectory() as directory, mock.patch("downloads.open_https", response):
            expected = sha256(payload).hexdigest()
            self.assertEqual(download_zip("https://example.com", Path(directory) / "valid.zip", f"sha256:{expected}"), expected)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                download_zip("https://example.com", Path(directory) / "invalid.zip", "sha256:incorrect")

    def test_retries_timeout_and_discards_partial_zip(self):
        payload = b"complete zip"
        broken = mock.Mock(status=200)
        broken.getheader.return_value = None
        broken.read1.side_effect = [b"an incomplete and longer first download", TimeoutError()]
        complete = mock.Mock(status=200)
        complete.getheader.return_value = str(len(payload))
        complete.read1.side_effect = [payload, b""]

        @contextmanager
        def response(stream):
            yield stream

        with TemporaryDirectory() as directory, mock.patch(
                "downloads.open_https", side_effect=[response(broken), response(complete)]) as fetch:
            path = Path(directory) / "release.zip"
            checksum = sha256(payload).hexdigest()
            self.assertEqual(download_zip("https://example.com/release.zip", path, f"sha256:{checksum}"), checksum)
            self.assertEqual(fetch.call_args_list, [mock.call("https://example.com/release.zip")] * 2)
            self.assertEqual(path.read_bytes(), payload)

    def test_download_reports_timeout_and_does_not_retry_invalid_certificate(self):
        for error, message, attempts in ((TimeoutError(), "下载超时", 2),
                                         (ssl.SSLCertVerificationError(), "证书", 1)):
            with self.subTest(message=message), TemporaryDirectory() as directory, mock.patch(
                    "downloads.open_https", side_effect=error) as fetch:
                with self.assertRaisesRegex(ValueError, message):
                    download_zip("https://example.com/release.zip", Path(directory) / "release.zip")
                self.assertEqual(fetch.call_count, attempts)

    def test_https_checks_transport_and_resolved_addresses(self):
        for url in ("http://example.com/x.zip", "file:///tmp/test.zip", "https://user@example.com/test.zip", "https://example.com:4242/test.zip"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                https_url(url)
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with mock.patch("downloads.socket.getaddrinfo", return_value=records), mock.patch("downloads.socket.create_connection") as dial:
            with self.assertRaisesRegex(ValueError, "局域网"):
                PublicHTTPSConnection("example.com").connect()
            dial.assert_not_called()


class PhoneTests(TestCase):
    def test_english_phone_form_includes_english_validation(self):
        session = PhoneInput("127.0.0.1", "repository", repository_from_url, language="en")
        self.addCleanup(session.close)
        connection = HTTPConnection(session.host, timeout=2)
        self.addCleanup(connection.close)
        path = f"/{session.token}"
        connection.request("GET", path)
        response = connection.getresponse()
        page = response.read().decode()
        self.assertIn('lang="en"', page)
        self.assertIn("Send to Deck", page)
        for url, status, message in (("https://example.com", 400, "Enter a GitHub repository or Releases URL."),
                                     ("https://github.com/owner/repo", 200, "URL sent.")):
            connection.request("POST", path, urlencode({"url": url}), headers={
                "Content-Type": "application/x-www-form-urlencoded", "Origin": f"http://{session.host}",
            })
            response = connection.getresponse()
            self.assertEqual(response.status, status)
            self.assertIn(message, response.read().decode())

    def test_form_keeps_same_origin_for_browser_post(self):
        session = PhoneInput("127.0.0.1", "zip", https_url)
        self.addCleanup(session.close)
        connection = HTTPConnection(session.host, timeout=2)
        self.addCleanup(connection.close)
        path = f"/{session.token}"
        connection.request("GET", path)
        page = connection.getresponse()
        self.assertEqual(page.status, 200)
        self.assertIn(b'<form method="post">', page.read())
        self.assertEqual(page.getheader("Referrer-Policy"), "same-origin")

        url = "https://example.com/plugin.zip"
        connection.request("POST", path, urlencode({"url": url}), headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"http://{session.host}",
        })
        result = connection.getresponse()
        self.assertEqual(result.status, 200)
        self.assertIn("地址已发送", result.read().decode("utf-8"))
        self.assertEqual(session.status(), {"status": "received", "url": url})

    def test_phone_posts_one_valid_url_with_no_install_action(self):
        session = PhoneInput("127.0.0.1", "repository", repository_from_url)
        self.addCleanup(session.close)

        def send(value, **headers):
            with_connection = HTTPConnection(session.host, timeout=2)
            try:
                with_connection.request("POST", f"/{session.token}", urlencode({"url": value}), headers={
                    "Content-Type": "application/x-www-form-urlencoded", **headers,
                })
                result = with_connection.getresponse()
                result.read()
                return result.status
            finally:
                with_connection.close()

        self.assertEqual(send("https://github.com/owner/repo", Origin="http://other.example"), 403)
        self.assertEqual(send("https://github.com/owner/repo", Origin="null"), 403)
        self.assertEqual(send("https://other.example"), 400)
        self.assertEqual(session.status(), {"status": "waiting"})
        self.assertEqual(send("https://github.com/owner/repo"), 200)
        self.assertEqual(send("https://github.com/other/repo"), 410)
        self.assertEqual(session.status(), {"status": "received", "url": "https://github.com/owner/repo"})


class PluginTests(IsolatedAsyncioTestCase):
    async def test_notification_rearms_only_after_install_and_supports_daily_checks(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            plugin = base / "plugins" / "Test"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text('{"name":"Test"}')
            package = plugin / "package.json"
            package.write_text('{"version":"1.0.0"}')
            with mock.patch.dict(os.environ, {"DECKY_PLUGIN_DIR": str(base / "plugins" / "Updater"),
                                             "DECKY_PLUGIN_SETTINGS_DIR": str(base / "settings"),
                                             "DECKY_PLUGIN_RUNTIME_DIR": str(base / "data")}):
                backend = Plugin()
                await backend.watch("Test", "https://github.com/owner/test")
                release = {"tag": "v1.1.0", "asset": asset("Test.zip")}
                with mock.patch("main.latest_release", return_value=release) as request:
                    await backend.check()
                    backend = Plugin()
                    self.assertEqual(await gather(backend.take_notifications(), backend.take_notifications()),
                                     [[{"name": "Test", "tag": "v1.1.0"}], []])
                    backend = Plugin()
                    await backend.check()
                    self.assertEqual(await backend.take_notifications(), [])
                    request.return_value = {"error": "releaseNetworkError"}
                    await backend.check()
                    self.assertEqual(await backend.take_notifications(), [])
                    request.return_value = {**release, "tag": "v1.2.0"}
                    await backend.check_plugin("Test")
                    self.assertEqual(await backend.take_notifications(), [])

                    package.write_text('{"version":"1.1.0"}')
                    backend._save(daily=True, last_checked=0)
                    await backend._check(True)
                    self.assertEqual(await backend.take_notifications(), [{"name": "Test", "tag": "v1.2.0"}])
                    self.assertEqual(await backend.take_notifications(), [])
                    package.write_text('{"version":"1.2.0"}')
                    await backend.check()
                    self.assertEqual(await backend.take_notifications(), [])

    async def test_check_one_plugin_keeps_other_watches_and_full_check_timestamp(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("Selected", "Other"):
                folder = base / "plugins" / name
                folder.mkdir(parents=True)
                (folder / "plugin.json").write_text(json.dumps({"name": name}))
                (folder / "package.json").write_text('{"version":"1.9.0"}')
            with mock.patch.dict(os.environ, {"DECKY_PLUGIN_DIR": str(base / "plugins" / "Updater"),
                                             "DECKY_PLUGIN_SETTINGS_DIR": str(base / "settings"),
                                             "DECKY_PLUGIN_RUNTIME_DIR": str(base / "data")}):
                backend = Plugin()
                await backend.watch("Selected", "https://github.com/owner/selected")
                await backend.watch("Other", "https://github.com/owner/other")
                backend._save(last_checked=123)
                release = {"tag": "v1.10.0", "asset": asset("Selected.zip")}
                with mock.patch("main.latest_release", return_value=release) as request:
                    await backend.check_plugin("Selected")
                    with self.assertRaisesRegex(ValueError, "不在监听列表"):
                        await backend.check_plugin("Absent")
                    with self.assertRaisesRegex(ValueError, "no longer watched"):
                        await backend.check_plugin("Absent", "en")
                    request.assert_called_once_with("owner/selected", "Selected")

                result = await Plugin().state()
                self.assertEqual(result["last_checked"], 123)
                self.assertEqual({watch["name"]: watch["status"] for watch in result["watches"]},
                                 {"Selected": "update", "Other": "unchecked"})

    async def test_watch_check_persist_and_reread_local_version(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            existing = base / "plugins" / "Test"
            existing.mkdir(parents=True)
            (existing / "plugin.json").write_text('{"name":"Test Plugin"}')
            package = existing / "package.json"
            package.write_text('{"version":"1.9.0"}')
            with mock.patch.dict(os.environ, {"DECKY_PLUGIN_DIR": str(base / "plugins" / "Updater"),
                                             "DECKY_PLUGIN_SETTINGS_DIR": str(base / "settings"),
                                             "DECKY_PLUGIN_RUNTIME_DIR": str(base / "data")}):
                backend = Plugin()
                result = await backend.watch("Test Plugin", "https://github.com/owner/repo")
                self.assertEqual(result["watches"][0]["status"], "unchecked")
                with mock.patch("releases.open_https", fake_release([asset("Test Plugin.zip")])):
                    result = await backend.check()
                self.assertEqual(result["watches"][0]["status"], "update")
                self.assertGreater(result["last_checked"], 0)
                self.assertTrue((await backend.set_daily(True))["daily"])
                backend = Plugin()
                package.write_text('{"version":"1.10.0"}')
                local = await backend.state()
                self.assertTrue(local["daily"])
                self.assertEqual(local["watches"][0]["status"], "current")
                with mock.patch("main.latest_release") as request:
                    await backend._check(True)
                    request.assert_not_called()
                self.assertEqual((await backend.unwatch("Test Plugin"))["watches"], [])
