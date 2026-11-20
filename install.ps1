# TruthProbe installer for opencode (Windows).
#
#   irm https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.ps1 -OutFile install.ps1
#   .\install.ps1                            # install into .\opencode-truthprobe
#   .\install.ps1 -Dir C:\src\opencode-tp    # custom directory
#   .\install.ps1 -DryRun                    # only check that the patch applies
#   .\install.ps1 -Uninstall                 # drop the patch commits, back to the base commit
#   .\install.ps1 -Scorer weights.json       # install your own scorer weights
#
# Steps: fetch sst/opencode at the base commit, apply
# patches/truthprobe-0001.patch, bun install, print the version.
# Requirements: git, bun (https://bun.sh). Nothing outside -Dir is modified.

[CmdletBinding()]
param(
  [string]$Dir = "opencode-truthprobe",
  [string]$Scorer = "",
  [switch]$DryRun,
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$Base = "007afb1b0c8a36dff93d7945909d4e976545ba95"
$BaseShort = "007afb1"
$Upstream = "https://github.com/sst/opencode.git"
$Repo = "https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master"
$PatchName = "patches/truthprobe-0001.patch"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "    $text" }
function Fail($text) { Write-Host "error: $text" -ForegroundColor Red; exit 1 }

Step "checking requirements"
try { $gitVersion = (git --version) } catch { Fail "git is required (https://git-scm.com)" }
Note $gitVersion
if (-not $Uninstall -and -not $DryRun) {
  try { $bunVersion = (bun --version) } catch { Fail "bun is required (https://bun.sh)" }
  Note "bun $bunVersion"
}

if ($Uninstall) {
  Step "uninstalling from $Dir"
  if (-not (Test-Path (Join-Path $Dir ".git"))) { Fail "$Dir is not a git checkout" }
  Push-Location $Dir
  $log = (git log --oneline -n 40 2>$null) -join "`n"
  if ($log -notmatch "truthprobe") {
    Note "no truthprobe commits found, nothing to remove"
    Pop-Location
    exit 0
  }
  Note "resetting the tree to $BaseShort (uncommitted edits to tracked files are lost)"
  git reset --hard $Base
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git reset failed" }
  git log --oneline -1
  Pop-Location
  Step "patch removed"
  exit 0
}

Step "fetching sst/opencode @ $BaseShort"
if (-not (Test-Path (Join-Path $Dir ".git"))) {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  Push-Location $Dir
  git init -q
  git remote add origin $Upstream 2>$null
  if ($LASTEXITCODE -ne 0) { git remote set-url origin $Upstream }
  git fetch -q --depth 1 origin $Base
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git fetch of $Base failed" }
  git checkout -q -B truthprobe FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git checkout failed" }
  Note "cloned into $((Get-Location).Path)"
} else {
  Push-Location $Dir
  Note "reusing existing checkout"
}

$log = (git log --oneline -n 40 2>$null) -join "`n"
if ($log -match "truthprobe") {
  Step "patch already applied, skipping"
} else {
  Step "downloading $PatchName"
  $patch = Join-Path ([System.IO.Path]::GetTempPath()) "truthprobe-0001.patch"
  Invoke-WebRequest -UseBasicParsing -Uri "$Repo/$PatchName" -OutFile $patch
  if (-not (Test-Path $patch) -or (Get-Item $patch).Length -eq 0) { Pop-Location; Fail "patch download failed" }

  Step "checking patch"
  git apply --check --whitespace=nowarn $patch
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "patch does not apply to $BaseShort; tree untouched" }
  Note "the patch applies cleanly"

  Step "applying patch"
  # git am needs committer identity; keep it local so the global config is untouched.
  git config user.name 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { git config user.name "TruthProbe" }
  git config user.email 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { git config user.email "truthprobe@localhost" }

  git am --whitespace=nowarn $patch
  if ($LASTEXITCODE -ne 0) {
    git am --abort 2>$null
    Note "git am failed, retrying as a plain diff"
    git apply --whitespace=nowarn $patch
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "patch did not apply; see the git output above" }
  }
  Remove-Item $patch -Force -ErrorAction SilentlyContinue
  git log --oneline -1
}

if ($Scorer -ne "") {
  Step "installing custom scorer weights"
  if (-not (Test-Path $Scorer)) { Pop-Location; Fail "no such weights file: $Scorer" }
  New-Item -ItemType Directory -Force -Path ".truthprobe" | Out-Null
  Copy-Item $Scorer ".truthprobe\weights.json" -Force
  Note "weights: $((Get-Location).Path)\.truthprobe\weights.json"
}

if ($DryRun) {
  Pop-Location
  Step "dry run: dependencies and build skipped"
  Write-Host ""
  Write-Host "Next:  .\install.ps1 -Dir $Dir"
  exit 0
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
Write-Host "Confidence appears under each answer as 'answer confidence 71% +- uncertain'."
Write-Host "Providers are probed automatically; verdicts live in"
Write-Host "%APPDATA%\opencode\truthprobe\capabilities.json. Switch the probe off with"
Write-Host "OPENCODE_TRUTHPROBE_PROBE=off, the whole feature off with OPENCODE_TRUTHPROBE=off."
Write-Host "Which models emit logprobs: docs/MODEL-SUPPORT.md."
if ($Scorer -ne "") {
  Write-Host ""
  Write-Host "Custom scorer weights installed. Enable them with:"
  Write-Host "  `$env:TRUTHPROBE_SCORER = `"linear:$location\.truthprobe\weights.json`""
}
