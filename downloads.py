from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPSConnection, HTTPException, IncompleteRead
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import stat
import time
from urllib.parse import urljoin, urlsplit
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED, ZIP_STORED
from zlib import error as CompressionError

from messages import message


MAX_DOWNLOAD = 128 * 1024**2
MAX_UNPACKED = 512 * 1024**2
MAX_MANIFEST = 256 * 1024
TUN_FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")
GITHUB_RELEASE_HOSTS = frozenset({
    "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
})


def https_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(message("请输入有效的公开 HTTPS 地址", "Enter a valid public HTTPS URL."))
    value = value.strip()
    if not value.isascii() or any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
        raise ValueError(message("请输入有效的公开 HTTPS 地址", "Enter a valid public HTTPS URL."))
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in {None, 443}):
        raise ValueError(message("仅支持公开 HTTPS 链接，不支持账号、密码或自定义端口",
                                 "Only public HTTPS links without credentials or custom ports are supported."))
    return parsed


class PublicHTTPSConnection(HTTPSConnection):
    def connect(self):
        records = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(record[4][0] for record in records))
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if self.host in GITHUB_RELEASE_HOSTS and self.port == 443 and ip in TUN_FAKE_IP_RANGE:
                continue
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise ValueError(message("不允许访问局域网、回环或保留地址", "Private, loopback and reserved addresses are not allowed."))
        last_error = None
        for address in addresses[:4]:
            try:
                connection = socket.create_connection((address, self.port), self.timeout)
            except OSError as error:
                last_error = error
                continue
            try:
                self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
            except BaseException:
                connection.close()
                raise
            return
        if last_error is not None:
            raise last_error
        raise OSError("无法连接下载服务器")


@contextmanager
def https_request(url, headers=None, *, method="GET", body=None, follow_redirects=False):
    request_headers = {"User-Agent": "UmeYc-Plugin-Updater", **(headers or {})}
    context = ssl.create_default_context()
    for system_ca in ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem"):
        if Path(system_ca).is_file():
            context.load_verify_locations(cafile=system_ca)
            break
    for _ in range(6):
        parsed = https_url(url)
        connection = PublicHTTPSConnection(parsed.hostname, timeout=10, context=context)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request(method, target, body=body, headers=request_headers)
            with connection.getresponse() as response:
                if follow_redirects and response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError(message("下载服务器没有给出重定向地址", "The download server did not provide a redirect URL."))
                    url = urljoin(url, location)
                    if https_url(url).hostname != parsed.hostname:
                        request_headers = {key: value for key, value in request_headers.items()
                                           if key.lower() != "authorization"}
                    continue
                yield response
                return
        finally:
            connection.close()
    raise ValueError(message("下载链接的重定向次数过多", "The download URL redirects too many times."))


def open_https(url, headers=None):
    return https_request(url, headers, follow_redirects=True)


def _download_zip_once(url, output, deadline):
    digest = sha256()
    size = 0
    with open_https(url) as response:
        if response.status != 200:
            raise ValueError(message(f"ZIP 下载失败（HTTP {response.status}）", f"ZIP download failed (HTTP {response.status})."))
        length = response.getheader("Content-Length")
        if length and (not length.isdigit() or int(length) > MAX_DOWNLOAD):
            raise ValueError(message("无法下载：ZIP 大小超过 128 MiB 或响应长度无效",
                                     "The ZIP exceeds 128 MiB or the response length is invalid."))
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError
            chunk = response.read1(256 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_DOWNLOAD:
                raise ValueError(message("ZIP 大小超过 128 MiB", "The ZIP exceeds 128 MiB."))
            try:
                output.write(chunk)
            except OSError as error:
                raise ValueError(message("无法写入 ZIP，请检查 Deck 的可用空间和权限",
                                         "Could not save the ZIP. Check free space and permissions on the Deck.")) from error
            digest.update(chunk)
        if length and size != int(length):
            raise IncompleteRead(b"", int(length) - size)
    return digest.hexdigest()


def download_zip(url, path, expected_digest=None):
    deadline = time.monotonic() + 120
    try:
        with path.open("xb") as output:
            for attempt in range(2):
                try:
                    checksum = _download_zip_once(url, output, deadline)
                except ssl.SSLCertVerificationError as error:
                    raise ValueError(message("无法验证 ZIP 下载服务器的证书，请检查 Deck 的日期和时间",
                                             "Could not verify the server certificate. Check the Deck’s date and time.")) from error
                except (OSError, HTTPException) as error:
                    if attempt == 0 and time.monotonic() < deadline:
                        output.seek(0)
                        output.truncate()
                        continue
                    if isinstance(error, TimeoutError):
                        raise ValueError(message("ZIP 下载超时，请检查 Deck 的网络后重试",
                                                 "ZIP download timed out. Check the Deck’s network and try again.")) from error
                    if isinstance(error, IncompleteRead):
                        raise ValueError(message("ZIP 下载不完整，请检查 Deck 的网络后重试",
                                                 "The ZIP download is incomplete. Check the Deck’s network and try again.")) from error
                    raise ValueError(message("无法连接或读取 ZIP 下载服务器，请检查 Deck 的网络和下载地址",
                                             "Could not reach or read from the ZIP server. Check the network and URL.")) from error
                if expected_digest and expected_digest.lower() != f"sha256:{checksum}":
                    raise ValueError(message("下载的 ZIP 与 GitHub 公布的 SHA-256 不一致",
                                             "The ZIP does not match the SHA-256 published by GitHub."))
                return checksum
    except OSError as error:
        raise ValueError(message("无法写入 ZIP，请检查 Deck 的可用空间和权限",
                                 "Could not save the ZIP. Check free space and permissions on the Deck.")) from error


def read_manifest(path, limit=MAX_MANIFEST):
    with path.open("rb") as source:
        return decode_manifest(source.read(limit + 1), limit)


def decode_manifest(data, limit=MAX_MANIFEST):
    if len(data) > limit:
        raise ValueError(message("插件清单太大", "The plugin manifest is too large."))
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError(message("插件清单无效", "The plugin manifest is invalid."))
    return value


def manifest_field(manifest, field):
    value = manifest.get(field)
    if (not isinstance(value, str) or not value.strip() or len(value) > 128
            or any(ord(char) < 32 or char in "/\\" for char in value)):
        raise ValueError(message(f"插件清单缺少有效的 {field}", f"The plugin manifest has no valid {field}."))
    return value.strip()


def inspect_zip(path):
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > 10000 or sum(member.file_size for member in members) > MAX_UNPACKED:
                raise ValueError(message("ZIP 为空或解压后过大", "The ZIP is empty or too large when extracted."))
            entries, roots = {}, set()
            for member in members:
                raw = member.orig_filename
                parts = raw.removesuffix("/").split("/")
                mode = (member.external_attr >> 16) & 0xFFFF
                if (any(part in {"", ".", ".."} or re.search(r"[\\:\x00-\x1f\x7f]", part) for part in parts)
                        or (len(parts) == 1 and not member.is_dir())
                        or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                        or member.flag_bits & 1 or member.compress_type not in {ZIP_STORED, ZIP_DEFLATED}):
                    raise ValueError(message("ZIP 含有不支持的文件、路径或压缩格式", "The ZIP contains an unsupported file, path or compression format."))
                key = tuple(parts)
                if key in entries:
                    raise ValueError(message("ZIP 含有重复路径", "The ZIP contains duplicate paths."))
                entries[key] = member.is_dir()
                roots.add(parts[0])
            if len(roots) != 1 or any(
                entries.get(key[:depth]) is False for key in entries for depth in range(1, len(key))
            ):
                raise ValueError(message("ZIP 必须只有一个插件目录，且目录结构有效", "The ZIP must contain one valid plugin folder."))
            folder = roots.pop()
            required = ((folder, "plugin.json"), (folder, "package.json"), (folder, "dist", "index.js"))
            if any(entries.get(key) is not False for key in required):
                raise ValueError(message("不是可安装的 Decky 成品：缺少清单或 dist/index.js",
                                         "This is not an installable Decky ZIP: missing manifests or dist/index.js."))

            def manifest(name):
                with archive.open(f"{folder}/{name}") as source:
                    return decode_manifest(source.read(MAX_MANIFEST + 1))

            plugin, package = manifest("plugin.json"), manifest("package.json")
            flags = plugin.get("flags", [])
            if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
                raise ValueError(message("插件的 flags 格式错误", "The plugin flags are invalid."))
            if archive.testzip() is not None:
                raise ValueError(message("ZIP 校验失败，请重新下载", "ZIP validation failed. Download it again."))
            return {"folder": folder, "name": manifest_field(plugin, "name"),
                    "version": manifest_field(package, "version"), "root": "root" in flags}
    except (BadZipFile, CompressionError, EOFError, UnicodeError, json.JSONDecodeError, TypeError, OSError) as error:
        raise ValueError(message("无法读取 ZIP 或插件清单，请使用 Release 中的 Decky 成品",
                                 "Could not read the ZIP or manifest. Use the Decky ZIP from the release.")) from error
