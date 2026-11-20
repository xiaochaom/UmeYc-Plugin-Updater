import json
import os
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from github_auth import CLIENT_ID_FILE, is_client_id


name = json.loads((root / "plugin.json").read_text(encoding="utf-8"))["name"]
files = ("plugin.json", "package.json", "main.py", "releases.py", "downloads.py", "github_auth.py",
         "phone_input.py", "messages.py", "README.md", "README.en.md", "dist/index.js", "dist/index.js.map")
for relative in files:
    if not (root / relative).is_file():
        raise SystemExit(f"Missing {relative}; run pnpm build first")
client_id = os.environ.get("UMEYC_GITHUB_CLIENT_ID", "").strip()
if client_id and not is_client_id(client_id):
    raise SystemExit("Invalid UMEYC_GITHUB_CLIENT_ID")
output = root / "out" / f"{name}.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for relative in files:
        archive.write(root / relative, f"{name}/{relative}")
    if client_id:
        archive.writestr(f"{name}/{CLIENT_ID_FILE}", client_id)
print(output)
