import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


root = Path(__file__).resolve().parents[1]
name = json.loads((root / "plugin.json").read_text(encoding="utf-8"))["name"]
files = ("plugin.json", "package.json", "main.py", "releases.py", "downloads.py",
         "phone_input.py", "messages.py", "README.md", "README.en.md", "dist/index.js", "dist/index.js.map")
for relative in files:
    if not (root / relative).is_file():
        raise SystemExit(f"Missing {relative}; run pnpm build first")
output = root / "out" / f"{name}.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for relative in files:
        archive.write(root / relative, f"{name}/{relative}")
print(output)
