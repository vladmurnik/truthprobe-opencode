# TruthProbe installer for opencode (Windows).
#
#   irm https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.ps1 | iex
#   .\install.ps1 [-Dir opencode-truthprobe]
#
# Steps:
#   1. fetch sst/opencode at the exact base commit the patch was built on;
#   2. apply patches/truthprobe-0001.patch (git am, or git apply as a fallback);
#   3. bun install, then print the binary version.
#
# Requirements: git, bun (https://bun.sh). Nothing outside -Dir is modified.

[CmdletBinding()]
param(
  [string]$Dir = "opencode-truthprobe"
)

$ErrorActionPreference = "Stop"

$Base = "007afb1b0c8a36dff93d7945909d4e976545ba95"
$BaseShort = "007afb1"
$Upstream = "https://github.com/sst/opencode.git"
$Repo = "https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master"
$PatchName = "patches/truthprobe-0001.patch"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "error: $text" -ForegroundColor Red; exit 1 }

try { $gitVersion = (git --version) } catch { Fail "git is required (https://git-scm.com)" }
try { $bunVersion = (bun --version) } catch { Fail "bun is required (https://bun.sh)" }
Step "checking requirements"
Write-Host "    $gitVersion"
Write-Host "    bun $bunVersion"

Step "fetching sst/opencode @ $BaseShort into $Dir"
if (Test-Path (Join-Path $Dir ".git")) {
  Write-Host "    reusing existing checkout"
  Push-Location $Dir
} else {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  Push-Location $Dir
  git init -q
  git remote add origin $Upstream 2>$null
  if ($LASTEXITCODE -ne 0) { git remote set-url origin $Upstream }
  git fetch -q --depth 1 origin $Base
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git fetch of $Base failed" }
  git checkout -q -B truthprobe FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git checkout failed" }
}

$patched = (git log --oneline -n 20 2>$null) -join "`n"
if ($patched -match "truthprobe") {
  Step "patch already applied, skipping"
} else {
  Step "downloading $PatchName"
  $patch = Join-Path ([System.IO.Path]::GetTempPath()) "truthprobe-0001.patch"
  Invoke-WebRequest -UseBasicParsing -Uri "$Repo/$PatchName" -OutFile $patch
  if (-not (Test-Path $patch) -or (Get-Item $patch).Length -eq 0) { Pop-Location; Fail "patch download failed" }

  Step "applying patch"
  # git am needs committer identity; keep it local so the global config is untouched.
  git config user.name 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { git config user.name "TruthProbe" }
  git config user.email 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { git config user.email "truthprobe@localhost" }

  git am --whitespace=nowarn $patch
  if ($LASTEXITCODE -ne 0) {
    git am --abort 2>$null
    Write-Host "    git am failed, retrying as a plain diff"
    git apply --whitespace=nowarn $patch
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "patch did not apply; see the git output above" }
  }
  Remove-Item $patch -Force -ErrorAction SilentlyContinue
}

Step "installing dependencies (a few minutes)"
bun install
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "bun install failed" }

Step "smoke test"
bun run --cwd packages/cli src/index.ts --version

$location = (Get-Location).Path
Pop-Location

Step "done"
Write-Host ""
Write-Host "Run it:"
Write-Host ""
Write-Host "  cd `"$location`""
Write-Host "  bun run --cwd packages/cli src/index.ts"
Write-Host ""
Write-Host "Providers are probed automatically: the first chat-completions request sends one"
Write-Host "'ping' with max_tokens: 1 and logprobs: true, and if the provider answers with"
Write-Host "logprobs, confidence is enabled for it from the next request on. Verdicts live in"
Write-Host "%APPDATA%\opencode\truthprobe\capabilities.json."
Write-Host "Turn the probe off with OPENCODE_TRUTHPROBE_PROBE=off."
