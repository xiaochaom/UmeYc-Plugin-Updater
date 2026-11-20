from contextlib import suppress
import json
import re
from urllib.parse import urlsplit

from downloads import open_https
from messages import message


REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", re.ASCII)
VERSION = re.compile(
    r"[vV]?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([\w-]+(?:\.[\w-]+)*))?(?:\+([\w-]+(?:\.[\w-]+)*))?", re.ASCII
)


def repository_from_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(message("请输入 GitHub 仓库地址", "Enter a GitHub repository URL."))
    value = value.strip()
    if value.lower().startswith("github.com/"):
        value = "https://" + value
    elif value.lower().startswith("git@github.com:"):
        value = "https://github.com/" + value[len("git@github.com:"):]
    if not value.isascii() or not value or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError(message("请输入有效的 GitHub 仓库地址", "Enter a valid GitHub repository URL."))
    parsed = urlsplit(value)
    parts = parsed.path.strip("/").split("/")
    if (parsed.scheme != "https" or parsed.netloc.lower() not in {"github.com", "www.github.com"}
            or len(parts) < 2 or (len(parts) > 2 and parts[2] != "releases")):
        raise ValueError(message("请输入 GitHub 仓库或 Releases 地址", "Enter a GitHub repository or Releases URL."))
    repo = f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if not REPOSITORY.fullmatch(repo) or repo.split("/")[1] in {".", ".."}:
        raise ValueError(message("请输入有效的 GitHub 仓库地址", "Enter a valid GitHub repository URL."))
    return repo.lower()


def repository_hint(value):
    if isinstance(value, dict):
        value = value.get("url")
    if not isinstance(value, str):
        return None
    url = value.strip()
    if url.lower().startswith("git+"):
        url = url[4:]
    for prefix in ("ssh://git@github.com/", "git://github.com/", "github:"):
        if url.lower().startswith(prefix):
            url = "https://github.com/" + url[len(prefix):]
            break
    try:
        return f"https://github.com/{repository_from_url(url)}"
    except ValueError:
        return None


def version_key(value):
    match = VERSION.fullmatch(value.strip()) if isinstance(value, str) and len(value) <= 128 else None
    if not match:
        return None
    prerelease, build = match.group(4, 5)
    if "_" in ((prerelease or "") + (build or "")):
        return None
    identifiers = (prerelease or "").split(".") if prerelease else []
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in identifiers):
        return None
    ordering = tuple((0, int(part)) if part.isdigit() else (1, part) for part in identifiers)
    return (*map(int, match.group(1, 2, 3)), prerelease is None, ordering)


def _integer_header(response, name):
    value = response.getheader(name)
    return int(value) if isinstance(value, str) and re.fullmatch(r"[0-9]{1,12}", value) else None


def latest_release(repo, plugin_name, token=None, rate_limit=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with open_https(f"https://api.github.com/repos/{repo}/releases/latest", headers) as response:
        remaining = _integer_header(response, "X-RateLimit-Remaining") if rate_limit is not None or response.status == 403 else None
        retry_after = _integer_header(response, "Retry-After") if response.status in (403, 429) else None
        if rate_limit is not None:
            rate_limit.update(remaining=remaining, reset_at=_integer_header(response, "X-RateLimit-Reset"),
                              retry_after=retry_after)
        if token and response.status == 401:
            return {"error": "releaseAuthExpired"}
        if response.status == 404:
            return {"error": "releaseNotFound"}
        if response.status == 429 or (response.status == 403 and (remaining == 0 or retry_after is not None)):
            return {"error": "releaseRateLimit"}
        if response.status == 403:
            with suppress(ValueError, AttributeError):
                detail = json.loads(response.read(8192)).get("message")
                if isinstance(detail, str) and "secondary rate limit" in detail.lower():
                    return {"error": "releaseRateLimit"}
        if response.status != 200:
            return {"error": "releaseHttpError", "http_status": response.status}
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        return {"error": "releaseTooLarge"}
    release = json.loads(payload)
    if release["draft"] or release["prerelease"]:
        return {"error": "releaseNoStable"}
    assets = [asset for asset in release["assets"] if asset["state"] == "uploaded"
              and asset["name"].lower().endswith(".zip")]
    matches = [asset for asset in assets if asset["name"].casefold() == f"{plugin_name}.zip".casefold()]
    asset = (matches or assets)[0] if len(matches or assets) == 1 else None
    return {
        "tag": release["tag_name"],
        "title": release["name"] or release["tag_name"],
        "notes": (release["body"] or "")[:30000],
        "published_at": release["published_at"],
        "asset": {"name": asset["name"], "url": asset["browser_download_url"], "digest": asset.get("digest")}
        if asset else None,
        "asset_error": "" if asset else ("multipleZips" if assets else "noZip"),
    }


def release_status(installed, release):
    if installed is None:
        return "missing"
    if not release:
        return "unchecked"
    if "error" in release:
        return "error"
    current, target = version_key(installed), version_key(release["tag"])
    if current is None or target is None:
        return "unknown"
    if current >= target:
        return "current"
    return "update" if release["asset"] else "no_asset"
