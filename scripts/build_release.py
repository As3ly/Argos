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
LOCK_FILE = ROOT / "uv.lock"
CORPORATE_UV_CONFIG_FILE = ROOT / "uv-corporate.toml"
PROXY_CONFIG_FILE = ROOT / "backend" / "proxy_config.py"
SPEC_FILE = ROOT / "Argos.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"
NEXUS_HOST = "nexus.framatome.corp"
NEXUS_INDEX_URL = "https://nexus.framatome.corp/repository/py-pypi/simple"
FRA_PROXY_URL = "http://163.116.128.80:8080"


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


def assert_corporate_constraints() -> None:
    lock_text = LOCK_FILE.read_text(encoding="utf-8")
    if NEXUS_HOST not in lock_text:
        raise RuntimeError("uv.lock ne pointe pas vers le Nexus corporate.")
    forbidden_public_indexes = ("https://pypi.org/simple", "https://files.pythonhosted.org/")
    forbidden_found = [value for value in forbidden_public_indexes if value in lock_text]
    if forbidden_found:
        raise RuntimeError(
            "uv.lock contient encore des URLs PyPI publiques: " + ", ".join(forbidden_found)
        )

    corporate_uv_config = CORPORATE_UV_CONFIG_FILE.read_text(encoding="utf-8")
    for expected in (NEXUS_INDEX_URL, "native-tls = true", FRA_PROXY_URL):
        if expected not in corporate_uv_config:
            raise RuntimeError(f"Contrainte corporate manquante dans uv-corporate.toml: {expected}")

    proxy_config = PROXY_CONFIG_FILE.read_text(encoding="utf-8")
    for expected in ("DEFAULT_HTTP_PROXY", "DEFAULT_HTTPS_PROXY", FRA_PROXY_URL):
        if expected not in proxy_config:
            raise RuntimeError(f"Proxy Fra manquant dans backend/proxy_config.py: {expected}")

    ssl_files = [
        ROOT / "backend" / "IAfiltre_async.py",
        ROOT / "backend" / "Scrapers" / "scrap_boamp.py",
        ROOT / "backend" / "Scrapers" / "scrap_ted.py",
    ]
    for path in ssl_files:
        text = path.read_text(encoding="utf-8")
        if "truststore.inject_into_ssl()" not in text:
            raise RuntimeError(f"Injection SSL truststore absente: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Windows release artifact for Argos.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check version consistency; do not run PyInstaller.",
    )
    args = parser.parse_args()

    version = assert_versions_match()
    assert_corporate_constraints()
    if args.check:
        print(f"Version OK: Argos {version}")
        print("Contraintes corporate OK: Nexus, proxy Fra, TLS natif uv, truststore runtime")
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
