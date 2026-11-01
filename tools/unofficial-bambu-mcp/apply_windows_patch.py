"""Apply the scoped project-basename fix to this local 0.3.0 installation only."""
import ast
import difflib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import sysconfig

PATCH_ID = "windows-project-basename-v1"
OLD = 'path.rsplit("/", 1)[-1].rsplit(".", 1)[0]'
NEW = 'os.path.splitext(os.path.basename(path))[0]'
BASE = Path(__file__).resolve().parent
EXPECTED_VENV = BASE / ".venv"
PATCH_DIR = BASE / "patches"
BACKUP = PATCH_DIR / "threemf.py.original"
REPORT = PATCH_DIR / "patch-report.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patched_bytes(data):
    text = data.decode("utf-8")
    if text.count(OLD) != 1 or NEW in text:
        raise RuntimeError("Original source must contain exactly one expected expression")
    tree = ast.parse(text)
    imports_os = any(isinstance(node, ast.Import) and any(alias.name == "os" for alias in node.names)
                     for node in tree.body)
    text = text.replace(OLD, NEW, 1)
    if not imports_os:
        newline = "\r\n" if "\r\n" in text else "\n"
        anchor = f"import json{newline}"
        if text.count(anchor) != 1:
            raise RuntimeError("Expected unique import json anchor was not found")
        text = text.replace(anchor, f"import json{newline}import os{newline}", 1)
    ast.parse(text)
    return text.encode("utf-8"), not imports_os


def main():
    if os.name != "nt":
        raise RuntimeError("This patch is scoped to the Windows installation")
    if Path(sys.prefix).resolve() != EXPECTED_VENV.resolve():
        raise RuntimeError("Run using this installation's .venv Python")
    version = importlib.metadata.version("unofficial-bambu-mcp")
    if version != "0.3.0":
        raise RuntimeError(f"Refusing to patch unsupported version {version}")
    target = Path(sysconfig.get_paths()["purelib"]) / "unofficial_bambu_mcp" / "threemf.py"
    if not target.resolve().is_relative_to(EXPECTED_VENV.resolve()):
        raise RuntimeError("Module is outside this isolated environment")
    current = target.read_bytes()
    text = current.decode("utf-8")
    if text.count(NEW) == 1 and OLD not in text:
        if not BACKUP.is_file():
            raise RuntimeError("Untracked existing modification: original backup is missing")
        original = BACKUP.read_bytes()
        expected, _ = patched_bytes(original)
        if expected != current:
            raise RuntimeError("Current source differs from the exact expected scoped patch")
        if not REPORT.is_file():
            raise RuntimeError("Patch report is missing")
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        if report.get("patch_id") != PATCH_ID or report.get("after_sha256") != sha(current):
            raise RuntimeError("Patch report does not match installed source")
        print(json.dumps({"status": "already_applied", "patch_id": PATCH_ID,
                          "after_sha256": sha(current), "report": str(REPORT)}))
        return
    patched, import_added = patched_bytes(current)
    PATCH_DIR.mkdir(exist_ok=True)
    if BACKUP.exists():
        if BACKUP.read_bytes() != current:
            raise RuntimeError("Existing original backup differs from current unpatched source")
    else:
        with BACKUP.open("xb") as handle:
            handle.write(current)
    if REPORT.exists():
        raise RuntimeError("A patch report already exists for an unpatched module")
    temporary = target.with_name(target.name + ".codex-patch.tmp")
    with temporary.open("xb") as handle:
        handle.write(patched)
        handle.flush()
        os.fsync(handle.fileno())
    if target.read_bytes() != current:
        temporary.unlink()
        raise RuntimeError("Module changed while preparing the patch")
    os.replace(temporary, target)
    if target.read_bytes() != patched:
        raise RuntimeError("Post-write hash verification failed")
    samples = {r"C:\qa\input_project.3mf": "input_project",
               r"C:\qa\project.v2.3mf": "project.v2"}
    for filename, expected_name in samples.items():
        assert os.path.splitext(os.path.basename(filename))[0] == expected_name
    report = {
        "patch_id": PATCH_ID, "version": version, "target": str(target),
        "original_backup": str(BACKUP), "before_sha256": sha(current),
        "after_sha256": sha(patched), "expression_replacements": 1,
        "import_os_added": import_added, "basename_checks": samples,
        "diff": "".join(difflib.unified_diff(current.decode("utf-8").splitlines(True),
                    patched.decode("utf-8").splitlines(True), fromfile="threemf.py.original",
                    tofile="threemf.py.patched", n=2)),
    }
    with REPORT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"status": "applied", "patch_id": PATCH_ID,
                      "before_sha256": sha(current), "after_sha256": sha(patched),
                      "report": str(REPORT)}))


if __name__ == "__main__":
    main()
