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
  if ($DryRun) {
    Pop-Location
    Step "dry run: would reset --hard $BaseShort, tree left untouched"
    exit 0
  }
  $dirty = (git status --porcelain 2>$null) -join ""
  if ($dirty -ne "" -and $env:TRUTHPROBE_ALLOW_DIRTY -ne "1") {
    Pop-Location
    Fail "$Dir has uncommitted changes; commit them or set TRUTHPROBE_ALLOW_DIRTY=1"
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
# `-DryRun` не трогает $Dir: reset --hard + checkout -B передвигают ветку и теряют
# локальные коммиты, поэтому проверка идёт в одноразовом клоне.
$tempClone = $null
if ($DryRun) {
  $tempClone = Join-Path ([System.IO.Path]::GetTempPath()) ("truthprobe-check-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $tempClone | Out-Null
  Push-Location $tempClone
  git init -q
  git remote add origin $Upstream
  git fetch -q --depth 1 origin $Base
  if ($LASTEXITCODE -ne 0) {
    # GitHub может отказать в необъявленном SHA: тогда тянем историю целиком.
    git fetch -q origin
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git fetch of $Base failed" }
  }
  git checkout -q -B truthprobe FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git checkout failed" }
  Note "checking in a temporary clone: $tempClone"
} elseif (-not (Test-Path (Join-Path $Dir ".git"))) {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  Push-Location $Dir
  git init -q
  git remote add origin $Upstream 2>$null
  if ($LASTEXITCODE -ne 0) { git remote set-url origin $Upstream }
  git fetch -q --depth 1 origin $Base
  if ($LASTEXITCODE -ne 0) {
    # GitHub может отказать в необъявленном SHA: тогда тянем историю целиком.
    git fetch -q origin
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git fetch of $Base failed" }
  }
  git checkout -q -B truthprobe FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git checkout failed" }
  Note "cloned into $((Get-Location).Path)"
} else {
  Push-Location $Dir
  Note "reusing existing checkout"
  $head = (git rev-parse HEAD 2>$null | Select-Object -First 1)
  $known = (git log --oneline -n 40 2>$null) -join "`n"
  if ($head -ne $Base -and $known -notmatch "truthprobe") {
    # Дерево на чужом коммите: без приведения к $Base патч не ляжет, а reset --hard
    # молча стирает незакоммиченные правки — поэтому сначала проверяем чистоту.
    $dirty = (git status --porcelain 2>$null) -join ""
    if ($dirty -ne "" -and $env:TRUTHPROBE_ALLOW_DIRTY -ne "1") {
      Pop-Location
      Fail "$Dir has uncommitted changes; commit them or set TRUTHPROBE_ALLOW_DIRTY=1"
    }
    Note "moving the checkout to $BaseShort"
    git fetch -q --depth 1 origin $Base
    if ($LASTEXITCODE -ne 0) {
      # GitHub может отказать в необъявленном SHA: тогда тянем историю целиком.
      git fetch -q origin
      if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git fetch of $Base failed" }
    }
    git reset -q --hard FETCH_HEAD
    git checkout -q -B truthprobe
  }
}

$log = (git log --oneline -n 40 2>$null) -join "`n"
if ($log -match "truthprobe") {
  Step "patch already applied, skipping"
} else {
  Step "downloading $PatchName"
  # Уникальное имя: фиксированный путь в %TEMP% можно подменить между записью и чтением,
  # а сам патч затем исполняется (bun install + сборка).
  $patch = Join-Path ([System.IO.Path]::GetTempPath()) ("truthprobe-" + [guid]::NewGuid().ToString("N") + ".patch")
  Invoke-WebRequest -UseBasicParsing -Uri "$Repo/$PatchName" -OutFile $patch
  if (-not (Test-Path $patch) -or (Get-Item $patch).Length -eq 0) { Pop-Location; Fail "patch download failed" }
  $hash = (Get-FileHash -Algorithm SHA256 -Path $patch).Hash.ToLower()
  if ($hash -ne "381b37d02024f6e30a43c1bd0002b360da55c4affe70309ac4f3ed387ccc4fe5") {
    Remove-Item $patch -Force -ErrorAction SilentlyContinue
    Pop-Location
    Fail "patch checksum mismatch: pinned 381b37d02024f6e30a43c1bd0002b360da55c4affe70309ac4f3ed387ccc4fe5, got $hash"
  }

  Step "checking patch"
  git apply --check --whitespace=nowarn $patch
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "patch does not apply to $BaseShort; tree untouched" }
  Note "the patch applies cleanly"

  if ($DryRun) {
    Remove-Item $patch -Force -ErrorAction SilentlyContinue
    Pop-Location
    if ($tempClone) { Remove-Item -Recurse -Force $tempClone -ErrorAction SilentlyContinue }
    Step "dry run: patch applies, $Dir untouched"
    Write-Host ""
    Write-Host "Next:  .\install.ps1 -Dir $Dir"
    exit 0
  }

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
