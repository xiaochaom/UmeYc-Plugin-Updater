from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import ipaddress
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs

from messages import message, use_language


def lan_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            address = connection.getsockname()[0]
        ip = ipaddress.ip_address(address)
        if ip.is_loopback or ip.is_unspecified or not ip.is_private:
            raise ValueError()
        return address
    except (OSError, ValueError) as error:
        raise ValueError(message("未找到局域网地址，请让手机和 Deck 连接同一 Wi-Fi",
                                 "No LAN address found. Connect the phone and Deck to the same Wi-Fi.")) from error


class PhoneInput:
    def __init__(self, address, mode, validator, timeout=300, language="zh"):
        self.token = secrets.token_urlsafe(32)
        self.mode = mode
        self.validator = validator
        self.language = "en" if language == "en" else "zh"
        self.value = None
        self.expires = time.monotonic() + timeout
        self.closed = False
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer((address, 0), PhoneHandler)
        self.server.session = self
        self.host = f"{address}:{self.server.server_port}"
        self.url = f"http://{self.host}/{self.token}"
        self.worker = threading.Thread(target=self.server.serve_forever, args=(0.1,), daemon=True)
        self.timer = threading.Timer(timeout, self.close)
        self.timer.daemon = True
        self.worker.start()
        self.timer.start()

    def status(self):
        with self.lock:
            if self.closed or time.monotonic() >= self.expires:
                return {"status": "expired"}
            if self.value is not None:
                return {"status": "received", "url": self.value}
            return {"status": "waiting"}

    def submit(self, value):
        with use_language(self.language):
            self.validator(value)
        with self.lock:
            if self.closed or time.monotonic() >= self.expires:
                raise TimeoutError()
            if self.value is not None:
                raise FileExistsError()
            self.value = value.strip()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        self.timer.cancel()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()


class PhoneHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *_args):
        pass

    def authorized(self):
        session = self.server.session
        if self.path != f"/{session.token}" or self.headers.get("Host") != session.host:
            self.send_error(404)
            return False
        return True

    def text(self, zh, en):
        return message(zh, en, self.server.session.language)

    def expired_page(self):
        self.page(self.text("二维码已用过或过期，请在 Deck 上重新生成。",
                            "This QR code has expired or been used. Generate a new one on the Deck."), status=410, form=False)

    def page(self, message="", status=200, form=True):
        repository = self.server.session.mode == "repository"
        title = self.text("发送 GitHub 仓库地址", "Send GitHub repository URL") if repository else self.text(
            "发送 Decky ZIP 下载地址", "Send Decky ZIP download URL")
        label = self.text("网址", "URL")
        submit = self.text("发送到 Deck", "Send to Deck")
        placeholder = "https://github.com/owner/repo" if repository else "https://example.com/plugin.zip"
        fields = (f'<form method="post"><label>{label}<input name="url" inputmode="url" '
                  f'placeholder="{placeholder}" autocomplete="off" maxlength="4096" required></label>'
                  f'<button type="submit">{submit}</button></form>') if form else ""
        body = (f'<!doctype html><html lang="{self.text("zh-CN", "en")}"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{title}</title><style>body{{background:#151c27;color:#eef4ff;font:16px system-ui;'
                'max-width:32rem;margin:3rem auto;padding:0 1.25rem}input,button{display:block;'
                'box-sizing:border-box;width:100%;font:inherit;margin:.8rem 0;padding:.7rem}'
                f'</style><h1>{title}</h1><p>{escape(message)}</p>{fields}</html>').encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.authorized():
            return
        status = self.server.session.status()["status"]
        if status == "waiting":
            self.page(self.text("手机只发送地址，安装和更新均在 Deck 上确认。",
                                "The phone only sends the URL. Confirm installs and updates on the Deck."))
        else:
            self.expired_page()

    def do_POST(self):
        if not self.authorized():
            return
        session = self.server.session
        if self.headers.get("Origin") not in {None, f"http://{session.host}"}:
            self.send_error(403)
            return
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self.send_error(415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError()
            values = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=2).get("url", [])
            if len(values) != 1:
                raise ValueError()
        except (UnicodeError, ValueError):
            self.page(self.text("请输入一个有效的网址。", "Enter one valid URL."), status=400)
            return
        try:
            session.submit(values[0])
        except (TimeoutError, FileExistsError):
            self.expired_page()
        except ValueError as error:
            self.page(str(error), status=400)
        else:
            self.page(self.text("地址已发送，请回到 Deck 确认。", "URL sent. Go back to the Deck to confirm."), form=False)
