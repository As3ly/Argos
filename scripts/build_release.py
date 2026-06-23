from __future__ import annotations

import hashlib
import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "backend" / "version.py"
PYPROJECT_FILE = ROOT / "pyproject.toml"
SPEC_FILE = ROOT / "Argos.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"


def read_app_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"APP_VERSION introuvable dans {VERSION_FILE}")
    return match.group(1)


def read_pyproject_version() -> str:
    data = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def remove_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_versions_match() -> str:
    version = read_app_version()
    pyproject_version = read_pyproject_version()
    if version != pyproject_version:
        raise RuntimeError(
            f"Version incoherente: backend/version.py={version}, pyproject.toml={pyproject_version}"
        )
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Windows release artifact for Argos.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check version consistency; do not run PyInstaller.",
    )
    args = parser.parse_args()

    version = assert_versions_match()
    if args.check:
        print(f"Version OK: Argos {version}")
        return 0

    print(f"Building Argos {version}")
    remove_dir(BUILD_DIR)
    remove_dir(DIST_DIR)
    RELEASE_DIR.mkdir(exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(SPEC_FILE)],
        cwd=ROOT,
        check=True,
    )

    source_exe = DIST_DIR / "Argos.exe"
    if not source_exe.exists():
        raise RuntimeError(f"Executable attendu introuvable: {source_exe}")

    release_exe = RELEASE_DIR / f"Argos-{version}-windows-x64.exe"
    shutil.copy2(source_exe, release_exe)

    checksum = sha256(release_exe)
    checksum_file = RELEASE_DIR / f"{release_exe.name}.sha256.txt"
    checksum_file.write_text(f"{checksum}  {release_exe.name}\n", encoding="utf-8")

    print(f"Release exe: {release_exe}")
    print(f"SHA256: {checksum}")
    print(f"Checksum file: {checksum_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
