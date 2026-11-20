<#
.SYNOPSIS
  Разворачивает пропатченное дерево opencode (Windows / PowerShell).

.DESCRIPTION
  Те же шаги, что в scripts/dev-setup.sh: клон sst/opencode на BASE,
  git am патча, bun install, truthprobe-тесты.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\dev-setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\dev-setup.ps1 -Dir C:\src\tp -SkipInstall
  powershell -ExecutionPolicy Bypass -File scripts\dev-setup.ps1 -Check
#>
param(
  [string]$Dir = "",
  [string]$Base = "007afb1b0c8a36dff93d7945909d4e976545ba95",
  [switch]$Check,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Patch = Join-Path $Root "patches\truthprobe-0001.patch"
if (-not $Dir) { $Dir = Join-Path $Root ".worktree\opencode" }
$Upstream = if ($env:TRUTHPROBE_UPSTREAM) { $env:TRUTHPROBE_UPSTREAM } else { "https://github.com/sst/opencode.git" }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "нужен git" }
if (-not (Test-Path $Patch)) { throw "нет $Patch" }

if ($Check) {
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("tp-check-" + [guid]::NewGuid().ToString("n"))
  try {
    Write-Host "== проверяю патч на чистой базе $Base"
    git clone -q --filter=blob:none --no-checkout $Upstream $tmp
    git -C $tmp checkout -q $Base
    git -C $tmp apply --check $Patch
    if ($LASTEXITCODE -ne 0) { throw "патч не ложится" }
    Write-Host "OK: патч ложится без конфликтов"
  } finally {
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  }
  exit 0
}

if (Test-Path (Join-Path $Dir ".git")) {
  Write-Host "== дерево уже есть: $Dir"
  $last = git -C $Dir log --oneline -1
  if ($last -match "TruthProbe|per-model calibration") {
    Write-Host "== патч уже применён"
  } else {
    Write-Host "== применяю патч"
    git -C $Dir -c user.name=TruthProbe -c user.email=dev@localhost am $Patch
    if ($LASTEXITCODE -ne 0) { git -C $Dir apply $Patch }
  }
} else {
  Write-Host "== клонирую $Upstream -> $Dir"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dir) | Out-Null
  git clone --filter=blob:none --no-checkout $Upstream $Dir
  git -C $Dir checkout -q $Base
  Write-Host "== применяю патч"
  git -C $Dir -c user.name=TruthProbe -c user.email=dev@localhost am $Patch
  if ($LASTEXITCODE -ne 0) { git -C $Dir apply $Patch }
}

if (-not $SkipInstall) {
  if (-not (Get-Command bun -ErrorAction SilentlyContinue)) { throw "нужен bun: https://bun.sh" }
  Write-Host "== bun install"
  Push-Location $Dir
  try {
    bun install
    Write-Host "== truthprobe-тесты"
    bun test test/truthprobe
  } finally {
    Pop-Location
  }
}

Write-Host ""
Write-Host "готово. дерево: $Dir"
Write-Host "  cd $Dir"
Write-Host "  bun test test/truthprobe"
Write-Host "  bun run --cwd packages/cli src/index.ts run `"...`""
Write-Host "дальше: docs/DEVELOPMENT.md"
