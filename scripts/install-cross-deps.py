#!/usr/bin/env python3
"""Ставит windows-бинарные optional-зависимости в bun-хранилище (isolated linker).

Нужно для кросс-сборки opencode под Windows из Linux: bun не скачивает
платформенные опциональные пакеты чужой ОС, а сборщик их требует.
"""
import json
import os
import pathlib
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(os.environ.get("OPENCODE_REPO", "/home/adik/src/opencode"))
STORE = ROOT / "node_modules" / ".bun"
TMP = pathlib.Path("/tmp/win-deps")
TMP.mkdir(parents=True, exist_ok=True)

WANT = sys.argv[1:] or ["win32"]


def package_dirs():
    """Все реальные пакеты в node_modules, включая scoped-каталоги @scope/name."""
    roots = set()
    for candidate in ROOT.rglob("node_modules"):
        depth = len(candidate.relative_to(ROOT).parts)
        if depth > 6:
            continue
        roots.add(candidate)
    seen = []
    for nm in sorted(roots):
        try:
            entries = list(nm.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.startswith("@"):
                for scoped in entry.iterdir():
                    if scoped.is_dir() and (scoped / "package.json").is_file():
                        seen.append(scoped)
            elif (entry / "package.json").is_file():
                seen.append(entry)
    return seen


def tarball(name: str, version: str) -> bytes:
    url = f"https://registry.npmjs.org/{name.replace('/', '%2F')}"
    with urllib.request.urlopen(url, timeout=90) as response:
        meta = json.load(response)
    resolved = meta["versions"].get(version)
    if resolved is None:
        resolved = meta["dist-tags"]["latest"]
    with urllib.request.urlopen(resolved["dist"]["tarball"], timeout=180) as response:
        return response.read()


def install(name: str, version: str, target: pathlib.Path) -> None:
    blob = tarball(name, version)
    archive = TMP / f"{name.replace('/', '_')}-{version}.tgz"
    archive.write_bytes(blob)
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            member.name = parts[1]
            tar.extract(member, target)
    print(f"installed {name}@{version} -> {target}")


def node_modules_of(pkg: pathlib.Path) -> pathlib.Path:
    """node_modules, внутри которого лежит пакет (учитывая @scope)."""
    parent = pkg.parent
    return parent.parent if parent.name.startswith("@") else parent


installed = 0
for _ in range(3):
    pending = []
    for pkg in package_dirs():
        try:
            data = json.loads((pkg / "package.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        base = node_modules_of(pkg)
        for dep, version in (data.get("optionalDependencies") or {}).items():
            if not any(token in dep for token in WANT):
                continue
            target = base / dep
            if target.is_dir():
                continue
            pending.append((dep, str(version), target))
    if not pending:
        break
    for dep, version, target in pending:
        try:
            install(dep, version, target)
            installed += 1
        except Exception as error:  # noqa: BLE001
            print(f"FAILED {dep}@{version}: {error}")

print(f"total installed: {installed}")
