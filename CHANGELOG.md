# 0.13.18 — 2026-11-23

The project speaks English now; Russian survives as an optional translation.

**Primary language.** `README.md`, `CHANGELOG.md`, `docs/*.md`, `PLAN.md` and `CONTRIBUTING.md` are
English originals. The Russian text moved to `README.ru.md` and `docs/ru/*.md` (14 files), and the two
are linked by a banner at the top of each file. `README.en.md` was removed — it was the mirror of a
Russian main file. The rule lives in `CONTRIBUTING.md`, section "Language".

**Code.** The thirty-first commit of the patch (`d54ac9f`) rewrites 28 files, 524 lines of Russian
comments, JSDoc, messages and test names, into English. Scripts, `Makefile`, the CI workflow and both
installers were rewritten the same way, with identical insert and delete counts per file, so behaviour
did not move.

**One slip, and its repair.** That rewrite also dropped the Cyrillic abbreviations and the Cyrillic
character ranges from `sentences.ts`, so Russian answers were split after `г.`, `т.е.` and `см.`; the
test that pinned that behaviour was rewritten to a Latin case instead of being kept. The thirty-second
commit (`5e8cee4`) restored the abbreviation list and the three character classes and added explicit
tests — `does not split Cyrillic abbreviations` and a Cyrillic case next to the Greek one in the
unicode matrix. The core suite is now 131 pass / 379 expect in 6 files.

**Also in this release**

- `install.sh` and `install.ps1` retry the patch download three times and, if
  `raw.githubusercontent.com` keeps answering `503 Backend.max_conn reached` (run
  [`45184432491`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45184432491) failed
  that way), fall back to the release asset. The fallback is served from `releases/latest/download`,
  so it depends on the current tag being published: with `v0.13.18` published it returns the same
  514 039 bytes as the patch, and the pinned checksum still decides whether the bytes are trusted.
- `install.ps1` was stored in cp1251 and read as UTF-8 (mojibake); the rewrite removed the last such
  lines.

**Measured.** Patch: 32 commits, 53 files, `+3638/−55`, 514 039 B, sha256
`4436386b5457eb2cb2187054c064187e7e70e8bcda3d99c4214ee392df606f34`; `bun test test` → 93 pass / 9 skip /
0 fail, 211 expect, 102 tests; the core suite in the patched tree → 131 pass / 0 fail, 379 expect.
CI run [`45207888021`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45207888021) on
`c1214eb` (the thirty-first commit) — 7 of 7 jobs success. The thirty-second commit was measured
locally (`131 pass / 379 expect`); it then entered the patch, and run
[`45256323762`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45256323762) on `0288f6e` applies that patch from `007afb1` and runs the
same suites — 7 of 7 jobs success. A third run,
[`45257273878`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45257273878) on `bbb4858`, repeats the whole matrix on the commit that only
records these ids, so the citation covers the documentation too. The release `v0.13.18` is published (id `455929364`, asset 514 039 B,
`digest: sha256:4436386b…6f34`), and `releases/latest/download/truthprobe-0001.patch` was
downloaded and hashed by hand: 514 039 bytes, the same `sha256` — it matches the pin in both
installers.

**What this does not prove.** The translations were verified against numbers, links and heading counts,
not by a native speaker. The live UI run was not repeated. The installer fallback was exercised by
hand against the published asset, not by CI: no job downloads the fallback URL.

# 0.13.17 — 2026-11-23

The `v0.13.16` release was published with the patch attached: the `scripts/release.sh` plan was
executed end-to-end for the first time with a real token.

**Measured (`GET /releases/tags/v0.13.16`).** Release `455465241`, `draft: false`,
`published_at: 2026-11-23T13:28:34Z`, asset `truthprobe-0001.patch`, `size: 347540`,
`state: uploaded`; GitHub itself computed
`digest: sha256:381b37d02024f6e30a43c1bd0002b360da55c4affe70309ac4f3ed387ccc4fe5` — it matches
the local `sha256sum` and the `PATCH_SHA256` pin in `install.sh:31`. The release description is 948 characters
from the 0.13.16 entry in `CHANGELOG.md`.

**How it was done.** Not with `curl`: in WSL requests to `api.github.com` aborted with
`curl: (56) Proxy CONNECT aborted` and code `000`, while `Invoke-RestMethod` from Windows answered `200`.
The same order (draft → upload → publish) was carried out in PowerShell; `docs/DEVELOPMENT.md` records
the workaround and its cause.

**What this does not prove.** `release.sh` was not executed with a real token — an equivalent request
plan was executed. Re-running `make release` on an already published tag was not tested.

# 0.13.16 — 2026-11-23

The release was not a reproducible procedure: tags were created by hand, and the patch
never made it into a GitHub Release even once.

**Added**

- `scripts/release.sh` — creates a GitHub Release for an existing tag, attaches
  `patches/truthprobe-0001.patch` as an asset and takes the description from this tag's entry in
  `CHANGELOG.md` (if there is no entry — from the top one, with a warning).
  Before touching the network it checks: the tag exists, the patch checksum matches the `PATCH_SHA256` pin in `install.sh`,
  `owner/repo` is parsed from `git remote get-url origin`. A re-run updates the release
  instead of failing. `--dry-run` prints the plan without a token and without the network.
- `make release` and `make release TAG=… DRY=1`.
- `docs/DEVELOPMENT.md` — the "Release" section.

**What this does not prove.** The script was not executed with a real token: `--dry-run` was checked
(tag `v0.13.15`, sha256 `381b37d0…`, 36 lines of description, 347 540 B asset) and the negative branches
(a non-existent tag → `exit 1`).

# 0.13.15 — 2026-11-23

The built `TruthProbe.exe` presented itself as an OpenCode build: the file properties said
`CompanyName: OpenCode` and `LegalCopyright: Copyright c 2026 OpenCode`, and `FileVersion` was
`2.3.0` — the version of the shell, not of the product. A fork shipped to users under its own name
must not look like someone else's application.

**Fixed**

- `packages/desktop/electron-builder.config.ts` — `brand()` fills `copyright` and
  `extraMetadata.author.name` from `OPENCODE_DESKTOP_COMPANY` (defaults to `OPENCODE_DESKTOP_APP`).
- `scripts/build-desktop.sh` — sets `OPENCODE_DESKTOP_COMPANY`, takes `OPENCODE_VERSION`
  from the repository `package.json` (the product version instead of 2.3.0) and at the end prints the signing state:
  without `WIN_CSC_LINK` it says plainly that the file is not signed.
- `docs/DEVELOPMENT.md` — the "Signing" section: how to build a signed build (`WIN_CSC_LINK`,
  `WIN_CSC_KEY_PASSWORD`), how to check `Get-AuthenticodeSignature`, a before/after metadata table.
- Patch regenerated: 30 commits, 53 files, +3626/−55, 347 540 B,
  sha256 `381b37d02024f6e30a43c1bd0002b360da55c4affe70309ac4f3ed387ccc4fe5`.

**Verified**

- Rebuild `bash scripts/build-desktop.sh --win` (30 commits, tree `1784470`), then
  `Get-Item … .VersionInfo` on `packages/desktop/dist/win-unpacked/TruthProbe.exe`:
  `ProductName: TruthProbe`, `FileDescription: TruthProbe`, `CompanyName: TruthProbe`,
  `FileVersion: 0.13.14`, `ProductVersion: 0.13.14.0`,
  `LegalCopyright: Copyright c 2026 TruthProbe`, `Signature: NotSigned`.
- `electron-builder` called `signtool.exe` itself for three files and, with no certificate, left them
  unsigned — the script states this instead of hiding it.

**Verified in CI.** Run [`45169068249`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45169068249) on `d64998e` — **7 of 7 jobs success**:
`repo tests`, `installer dry-run` on ubuntu and windows, `patched tree` on ubuntu and windows,
`end-to-end verdict`, `cli build`.

**What this does not prove.** Signing was not verified with a real certificate: there is none. Launching
the application after the metadata change was not tested — the GUI is not started at the user's request.

# 0.13.14 — 2026-11-23

`cli-stages.test.ts` covered only directories like `2.0.18`, while a stamped build puts the CLI
in `0.0.0-dev-<ts>-<sha>-x64`. Both kinds are covered now — and so is the fact that the file launches at all.

**What turned out to be untrue.** The 0.13.9 report stated that `cli-stages.test.ts` "does not
run locally — no `@effect/platform-node`". The dependency exists: `@effect/platform-node: "catalog:"`
in the `devDependencies` of the `packages/desktop` package, and the test runs from the package directory
(`bun test src/main/service/cli-stages.test.ts`). The mistake was that the run was made from the repository
root, where the package has no `node_modules` of its own. The entry is corrected here instead of being left hanging.

**Added** — `packages/desktop/src/main/service/cli-stages.test.ts`, three cases against the real
`cleanStages` layout:

- upgrading from one stamped build to another — the old stamped directory is deleted;
- an accepted service installed by the previous stamped build — the directory is kept (`keep`);
- a regular release `2.0.32-x64` next to a forgotten stamped directory — the foreign directory is deleted.

**Verified**

- `bun test src/main/service/cli-stages.test.ts` → 7 pass / 0 fail / 14 expect.
- `bun test src/main/service/cli-version.test.ts src/main/service/cli-stages.test.ts` → 22 pass / 0 fail.
- The whole desktop package: `bun test` → 539 tests, 535 pass / 4 skip / 0 fail, 1 761 expect, 68 files.
- `bun run typecheck` in `packages/desktop` → 3 571 files, 0 errors.
- Patch regenerated: 29 commits, 53 files, +3617/−55, 345 729 B,
  sha256 `ff9312863c16d79e1e7064462a286bf25cebe57fe75c80ca76ea45e184ce43c1`.

**Verified in CI.** Run [`45165859105`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45165859105)
on `021059b` — **7 of 7 jobs success**: `repo tests` (including `docs numbers match the patch`),
both `installer dry-run`, both `patched tree` (with the three new stage cases),
`end-to-end verdict` and `cli build`. No red jobs.

**What this does not prove.** Only stage unit tests run; the live scenario "the application brought the
service up, updated to a new build, killed the old directory" still has not been tested —
the GUI was not started.

# 0.13.13 — 2026-11-23

Run [`45162922783`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45162922783) on `5e0191e`
did not fail because of the code: the `oven-sh/setup-bun@v2` step in the `patched tree (ubuntu-latest)` job finished
after three seconds with `Error: Unexpected HTTP response: 403`, the other six jobs (including both
installers, `repo tests` and `end-to-end verdict`) were green, and `cli build` did not start
because it depends on the failed job.

**Cause.** `bun-version: latest` makes the action resolve `latest` through the GitHub API;
anonymous requests from shared runners hit 403.

**Fix.** All five `setup-bun` steps now request a concrete version (`bun-version: 1.4.5` —
the same as locally) and pass `github-token: ${{ secrets.GITHUB_TOKEN }}` so they do not stay
anonymous. The workflow content was checked with `yaml.safe_load`.

**Verified in CI.** Run [`45163760974`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45163760974) on `b9b6212` — **7 of 7 jobs success**:
`patched tree` on both OSes (the `setup-bun` step passes), `installer dry-run` on both OSes,
`repo tests` with `docs numbers match the patch`, `end-to-end verdict`, `cli build`.

# 0.13.12 — 2026-11-23

A CI check through the API showed that every run since 0.13.8 had been red: two defects were
in the repository itself, not in the patch code.

**1. The pinned sha256 of the patch was not updated.** `install.sh` and `install.ps1` hold
`PATCH_SHA256` and compare the downloaded patch against it. After every patch regeneration the checksum
stayed the same, so `install.sh --dry-run` and `install.ps1 -DryRun` failed the comparison —
exactly those jobs were red. Now `scripts/make-patch.sh` recomputes the checksum and
rewrites it in both installers.

**2. The protocol test contradicted the README.** `test/opencode-tree/protocol.test.ts` required
that `capabilities.logprobs: false` win over `OPENCODE_TRUTHPROBE=1`, while the README promises
the opposite: an explicit variable asks for `logprobs` from all chat-completions models. The test was rewritten
to the promised behaviour (`an explicit environment override wins over capabilities`) plus
a separate case "without the variable, capabilities decide".

**3. Robust base fetch.** `git fetch --depth 1 origin <sha>` is not always served by GitHub:
for an unadvertised object the server refuses. Both installers fall back to a full
`git fetch` and verify that the base actually appeared.

**4. `make docs-check` in CI.** The `repo tests` job now compares the numbers in the docs with the patch.

**Verified in CI:** run [`45161855972`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45161855972) on `a8fb2d8` — **7 of 7 jobs success**:
`repo tests` (together with the new `docs numbers match the patch`), `installer dry-run` on Ubuntu
and Windows, `patched tree` on both OSes, `end-to-end verdict`, `cli build`. The previous five
runs (0.13.8–0.13.11) were red.

**Verified in CI:** run [`45161855972`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45161855972) on `a8fb2d8` — **7 of 7 jobs success**:
`repo tests` (together with the new `docs numbers match the patch`), `installer dry-run` on Ubuntu
and Windows, `patched tree` on both OSes, `end-to-end verdict`, `cli build`. The previous five
runs (0.13.8–0.13.11) were red.

**Verified locally:** `TRUTHPROBE_REQUIRE_PROTOCOL_TESTS=1 bun test
test/truthprobe-protocol.test.ts` in the patched tree — 9 pass / 0 fail; `make patch`
rewrites the pin (checked on a deliberately corrupted checksum — restored); `make docs-check`
green; `bun test test` — 101 tests, 0 fail.

# 0.13.11 — 2026-11-23

An audit of the 0.13.9 fix found an edge case in `splitStamp` that reproduced exactly the
timeout the stamp was split for in the first place.

**What it was.** `splitStamp("2.0.32+")` returned `{ version: "2.0.32+", stage: "2.0.32+" }`:
a trailing plus in the file counted as "no stamp". The version `2.0.32+` does not match `2.0.32`, which the
CLI writes about itself into `service.json`, so the service was again deemed foreign and restarted
until `Timed out waiting for the background service to start`.

**Fix.** The version is always the text before the separator; a leading plus means there is no
version in the file at all, and such a file counts as unstamped. Tests: the trailing-plus case expects
the trimmed version, `keptStages` keeps the stamped directory (`+` → `-`), a separate test
checks the invariant "the compared version never contains `+`".

**Verified:** `bun test src/main/service/cli-version.test.ts` — 15 pass / 0 fail; typecheck of all
packages — one run, 0 errors (schema 132, ai 357+322, core 2 036,
client 181, tui 1 947, session-ui 384, app 2 447, desktop 3 571 files);
desktop typecheck — 3 571 files, 0 errors. Patch regenerated: 28 commits, 52 files,
+3573/−55, 342 760 B.

# 0.13.10 — 2026-11-23

The patch assembled in 0.13.8 carried a copy of itself into the foreign tree, and the docs promised
a variable that no longer exists. Both are gone; the numbers are recomputed from the artefact.

**The patch no longer carries itself.** Commit 10/27 ("confidence levels and sentence
highlights") added the file `patches/truthprobe-0001.patch` — a stale set of nine
commits, 3 735 lines. Anyone who found it in their opencode clone and applied it would have
gotten the version before 0.13.x: without the capability probe, without the scorer, without the desktop flag. The file
was removed from the history `007afb1..HEAD` (27 commits preserved), `git log -- patches/…` over the
range is empty.

**A gate in `scripts/make-patch.sh`.** Before generating, the script checks
`git diff --name-only $BASE..HEAD` and fails if the range contains paths outside `packages/**`
and `bun.lock`. That is exactly how the patch copy slipped through.

**`make docs-check`.** The new `scripts/check-docs.sh` counts commits, files and bytes straight
from the patch file and compares them with `README.md`, `README.en.md`, `docs/VALIDATION.md` and
`CHANGELOG.md`; the target is part of `make verify`. The numbers in the docs no longer rest on an honest
word: a mismatch fails the check.

**Docs brought to the measured values:** 52 files, +3573/−55, patch 342 760 B;
`TRUTHPROBE_SHAKY_THRESHOLD` described as removed in 0.13.8 instead of "parsed but does not
affect"; the `git am` recipe contains a local identity (without it `empty ident name`, exit
128); the flag threshold is a strict `r > 0.45`; 127 tests replaced with 129; the section map of
`VALIDATION.md` brought up to §24; desktop typecheck — 3 571 files.

**Verified:** `bun test test` 93 pass / 9 skip / 0 fail, 211 expect, 102 tests;
`git apply --check` on a clean worktree `007afb1` passes; `git am` with a local identity
applies all 28 commits. The application was not launched (verified by code and logs).

# 0.13.9 — 2026-11-23

The version stamp added in 0.13.8 broke desktop startup: the application did not wait for the background
service and failed with `Timed out waiting for the background service to start`.

**Cause.** `resources/opencode-cli.version` went into `serviceVersion` whole, while the CLI writes
its own version without the stamp into `service.json` (`0.0.0-dev-<timestamp>`). `matchesVersion`
compares strings strictly, so `<version>+<sha256>` never matched: the service was deemed foreign,
was stopped, brought up again, and so on until the 120 second timeout.

**Fixed**

- `packages/desktop/src/main/service/cli-version.ts` — `splitStamp()`: before `+` is the version the service
  must report about itself, the whole string is the key of the directory with the build stage.
- `desktop-cli.ts` — `Resolved` carries `version` and `stage` separately: the stage directory is built from
  `stage`, the version for `Service.ensure` is taken from `version`.
- `background-service.ts`, `sidecar-probe.ts` — use the split values.
- `scripts/build-desktop.sh` — the version is taken from the binary itself (`opencode-cli --version`), not from the
  file next to it: that one holds a truncated `0.0.0-dev`, which is why the stamp used to come out empty.
- `scripts/install-desktop.sh` — `taskkill.exe /IM` with a single slash and waiting for the process to exit:
  with `//IM` in WSL `taskkill` did not recognise the argument, the application stayed running, and `cp` failed
  with `Permission denied`.

**Verified**

- desktop typecheck: 3 571 files, 0 errors; `cli-version` and `cli-stages` tests: 17 pass / 0 fail.
- A build with the stamp `0.0.0-dev-202611231000+c3c4a36e358e`, installed into
  `AppData/Local/Programs/TruthProbe`, CLI cache cleared.
- Startup log: `v2 CLI version bundled` with `version: '0.0.0-dev-202611231000'` and
  `stage: '0.0.0-dev-202611231000+c3c4a36e358e'`, then `v2 CLI background service ready` with
  `runningVersion: '0.0.0-dev-202611231000'`, `probed: true`; `service.json` contains the same version.
  No timeout.

# 0.13.8 — 2026-11-23

An external audit of the code (not of the numbers) found nine places where the behaviour diverged from the promises.
All are fixed in the patched tree, the patch is regenerated, desktop is rebuilt.

**Fixed in the core**

- `digitDensity` divided the digit count by `text.length`, i.e. by UTF-16 units: on emoji and astral
  CJK the digit share was understated. Now the numerator and denominator are counted in code points.
- `Math.min(...lps)` spread a long answer into arguments and could fail with `RangeError` right in
  event publication. Replaced by the `minOf(values)` fold.
- On token offset drift `sentences` stayed empty, and from the outside this read as "no doubtful
  sentences". Now everything is folded into one pseudo-sentence with the real text range,
  and the cause is written into `reason`.
- The `meanLp` feature was computed as `log(max(geo, 1e-9))`: everything below `1e-9` collapsed into one number
  −20.7, and the linear model lost resolution on bad answers. The raw mean logprob now goes into the features.
- The doubtful sentence flag was set at `risk >= riskyThreshold`, so exactly at the boundary
  (score 0.55 / risk 0.45) a sentence was marked doubtful while the level stayed `uncertain`.
  Now a strict `risk > riskyThreshold`.
- An estimate from hidden reasoning tokens was published with status `ok`, i.e. passed off as complete.
  Now `partial`, and the TUI prints ` · partial match`.

**Fixed in the UI and settings**

- `session-ui` and the TUI repeated the level thresholds as numbers (`0.9/0.75/0.55/0.35`), copying
  `packages/core/src/truthprobe/levels.ts`. Both read `LEVEL_BOUNDS` from there; `session-ui`
  gained a workspace dependency on `@opencode/core`.
- `TRUTHPROBE_SHAKY_THRESHOLD` was parsed into an option, but no scorer and no UI read it.
  The variable and the `shakyThreshold` field are removed — the setting no longer promises what does not exist.
- The `digitDensity` test pinned exactly the defect (division by UTF-16) and was rewritten for code points.
  Two tests were added: the estimate does not disappear on offset drift, and the flag is not set at the exact boundary.

**Verified**

- `packages/core/test` — 129 pass / 0 fail, 361 expect, 6 files; `session-ui` doubtful — 9 pass;
  typecheck core / session-ui / tui green.
- Patch: 26 commits, 48 files, +7234/−40, 491 498 B; `git apply --check` on `007afb1` passes.
- Desktop rebuilt: stamp `0.0.0-dev+ef470da66c44`, in the built CLI
  `TRUTHPROBE_SHAKY_THRESHOLD` is absent (grep → 0), the installed copy carries the same stamp.

**What this does not change.** Detector quality: `1 − exp(meanLp)` stays 0.799 OOF AUROC, the trained
weights still do not beat the formula (see 0.13.7). These are fixes of honesty and units, not of accuracy.

# 0.13.7 — 2026-11-22

A check of our own numbers by third-party agents found an error in the dataset on which the
metrics of the trained detector were computed. The numbers are withdrawn, the weights removed from the repository.

**Why it was broken**

- In **52 of 102** "false" answers the `answer` field turned out to be an empty string at `n_tokens = 160`
  (`max_tokens` limit): the model answered, the tokens were saved, the text did not make it into the dataset.
  The label was applied mechanically, and the empty string got `wrong` because neither the expected
  words nor refusal signs were found in it. Half of the negative class was a collection artefact.
- The text was restored by joining tokens from `rows_raw2.jsonl` and `rows_raw3.jsonl`; the same labelling rules
  as in the collector were applied to the restored text. Of the 52 restored, **26 turned out to be
  correct** answers, and the set became: **76 fabrications and 189 correct** (was 102 and 163).

**What the re-evaluation showed (`docs/LEARNED-WEIGHTS.md`)**

- The built-in formula `1 − exp(meanLp)` — OOF AUROC **0.799**, CI `[0.719, 0.872]`.
- Logistic regression on five product features — **0.783**, CI `[0.696, 0.867]`; on 26 features without
  length — **0.815**, CI `[0.737, 0.883]`. The difference from the formula covers zero:
  `Δ = −0.016 [−0.057, +0.020]` and `+0.016 [−0.036, +0.069]`.
- Removing the linear contribution of `n_tokens` drops quality to chance: **0.541** (5 features)
  and 0.717 (26 features).
- Within categories that have both classes, AUROC is 0.329–0.470: on `fake-work` all three estimates are **worse
  than chance**.
- 218 of 265 rows (82%) have a label fully determined by the question.

**Removed**

- `data/weights-detector.json` — the trained detector weights. The promise "we catch 75% of fabrications at 13%
  false alarms" is withdrawn: it was computed on the corrupted set, and on the corrected one the trained model
  is no better than the built-in formula.

**Added in `scripts/halluc/`**

- `repair.py` — text restoration from tokens and re-labelling; the result is written to `*f.jsonl`,
  the source files are not overwritten.
- `eval.py` — AUROC table, clustered bootstrap by `qid`, AUROC by category and by length quartiles.
- `dataset.py`, `score_all.ts` accept paths via `RAW2/RAW3/SCORED2/SCORED3`/`DATASET_OUT`,
  `SCORE_MODULE` — instead of hardcoded absolute paths.

**Fixed along the way**

- `dataset.py` and `score_all.ts` read the **restored** runs by default (`rows_raw2f.jsonl`,
  `rows_raw3f.jsonl`): before, the order of steps was pinned nowhere, and a run on the source files silently
  returned the corrupted set (102/163 with 52 empty instead of 76/189 without empty).
- Relative paths from `RAW2`/`RAW3` are resolved from `HALLUC_DIR`, not from the current directory.
- `scripts/make-patch.sh` printed 112 "files" instead of 46: it counted `diff --git` headers, not
  unique paths. Now `sort -u` over the paths.

**Desktop**

- `scripts/build-desktop.sh` writes the `opencode-cli.version` stamp as `<build version>+<sha256[:12]>`.
  Before, the stamp was not rebuilt, and the application kept taking the CLI from the cache by the old version string:
  the 22.11.2026 build was installed but ran on the binary from the 19th.
- `scripts/install-desktop.sh` + `make desktop-install`: copying the build into
  `AppData/Local/Programs/TruthProbe`, closing the running application and **clearing the CLI cache**;
  `--dry-run` shows what will be done.

# 0.13.6 — 2026-11-22 (numbers withdrawn, see 0.13.7)

The trained weights for the auxiliary fabrication detector now live in the repository in a format
that the patch can already load.

**Added**

- `data/weights-detector.json` — a linear model on five product features (`meanLp`, `minLp`,
  `meanPhi`, `fracLow`, `digitDensity`): OOF AUROC 0.881 on 265 rows (102 false, 68 questions,
  4 models). Length features are excluded from training. Standardisation is folded into the raw weights
  (`max|Δp| = 6.1e-16`), signs are flipped for confidence semantics: `score` is the probability
  that "the answer is correct", so the standard levels apply to it as usual.
- `docs/LEARNED-WEIGHTS.md` — what is inside, operating points (0.35 → 95.1% / 33.7%, 0.55 → 75.5% /
  12.9%, 0.65 → 62.7% / 9.2%), the enabling command, limitations and the section "what this does not prove"
  (a small set, failed transfer to `glm-5.3-flash`, the prompted nature of the negatives).
- `README.md`: a short section linking to the document.

Enabled without rebuilding the patch: `install.sh --scorer data/weights-detector.json` or
`TRUTHPROBE_SCORER=linear:<path>`.

# 0.13.5 — 2026-11-22

Training a fabrication detector on collected answers: 265 rows, 102 false, 68 questions, 4 models.
The result comes with caveats, and no model is ready to ship.

**Added**

- `scripts/halluc/`: `collect3.py` (31 trick questions), `score_all.ts`, `dataset.py`
  (30 features from tokens and text), `train.py` (logistic regression, CART, random forest, a mini-MLP on
  stdlib — numpy/sklearn are not available in the environment), `ablate.py`, `thresholds.py` and `README.md`.
- `docs/VALIDATION.md` §21: methodology, tables, ablations, `leave-one-model-out`, caveats.

**Measured**

- A single formula `exp(meanLp)` separates false from correct answers with AUROC **0.886**; the trained
  logistic regression without length features — **0.931**, random forest — **0.938**.
- Length features are excluded from the main experiment: `n_tokens` alone gives 0.973, because
  fabrications are long and control correct answers are short.
- The signal is not the mean confidence but the spread: `frac_below_half` 0.838, `std_lp` 0.835.
- Transfer to an unseen model: 0.939 / 0.974 / 0.961 for deepseek and particle, **0.500** for
  `glm-5.3-flash` — the detector is not universal.
- The product thresholds do not fit this class of error: at `score < 0.55` the flag never fired on any
  of the 102 false answers; at `score < 0.90` 98% of false answers were caught, but also 42% of correct ones.

**Not done**

- The detector is not wired into the product: there is no second independent set, 102 negatives are too few for
  calibration, and transfer between models failed on one of four.

# 0.13.4 — 2026-11-22

The first measurement on spontaneous hallucinations. The result is negative: token confidence
does not catch such fabrications.

**Measured** (`docs/VALIDATION.md` §20)

- 40 questions × 4 free-pi gateway models, `temperature 0`, 156 answers, two instructions.
- Free instruction: the models either answer correctly or outright refuse — after manual verification,
  of 16 "false" answers 0 turned out to be false (9 refusals, 7 correct with a caveat). Nothing to measure.
- Instruction "answer as if the premise were true": 32 false answers, of which 12 are measurable
  (the gateway did not return logprobs for the rest). AUROC **0.769**, mean score of correct answers 0.9625 versus 0.9217
  for false ones; **all 12** false answers ≥ 0.55, **8 of 12** ≥ 0.90 (`safe`).
- Examples: "Napoleon won the Battle of Waterloo in 1815" — 0.9573 `safe`; "the Great Wall is the
  only man-made object visible from space" — 0.9903 `safe`; the invented chemist Voskoboinikov —
  0.8352 `likely`.

**Not changed**

- Neither the formula nor the thresholds: fitting a threshold to twelve points would be fitting, not measuring.
  The conclusion for the interface is the same — the score shows the smoothness of generation, not truthfulness.

# 0.13.3 — 2026-11-22

A re-audit by five independent agents checked that 0.13.2 really closed what was
promised. Some items there were claimed but not done — below is what actually had to be finished,
and the places where the behaviour diverged from the documentation.

**Fixed**

- `packages/ai` (`truthprobeEnabled`): an explicit `OPENCODE_TRUTHPROBE` now overrides
  `capabilities.logprobs`. After a successful probe the plugin itself writes `true` there, so before,
  `OPENCODE_TRUTHPROBE=off` stopped working on a verified model. The flag is compared ignoring
  case and whitespace.
- `packages/core` (auto-check plugin): the cache key and model enabling are taken by the model
  that was actually checked (`model` from the request body), not by the catalogue name.
- `packages/core` (`parseLinearWeights`): strings, arrays and booleans no longer pass as numbers
  (`Number("") === 0`); a coefficient must be a number.
- `packages/core` (`publish-llm-event`): the reasoning-token estimate is taken once and
  cleared on abort — otherwise it stuck to the next text block.
- `packages/tui`: doubtful sentences are printed only when a signal is present, the number is omitted
  when the index is absent (it used to be `#NaN`), and with an old part without `level` there is a fallback to the flag.
- `scripts/collect.py`: the degenerate `phi` branch returned `1 − exp(logprob)` instead of
  `exp(logprob)` — the opposite sign relative to the runtime.
- `scripts/calibrate.py`: `--demo` and the docstring example mark `phiDef: "confidence"`;
  when converting unmarked rows a warning is printed.
- `install.sh`, `install.ps1`: `--dry-run` no longer moves the branch and does not do `reset --hard`
  (the check happens in a throwaway clone); `--uninstall` respects `--dry-run` and refuses to wipe
  uncommitted edits; a missing `sha256sum`/`shasum` is an error, not a skipped check.
- Tests: two tautologies removed (`risk = 1 − score` is the definition), checks added for
  the flag priority over the catalogue, strict weight parsing and the level fallback to the flag.
- `docs/VALIDATION.md`: the promise that score is the probability of truth removed; `+0.034` replaced with
  the measured `+0.014`; for the duplicate section numbers (§9/§10) the numbers are fixed to 18/19.

**Patch**

- `patches/truthprobe-0001.patch` rebuilt: 25 commits, 46 files, +7162/−40, 473 067 B.
  `git am` on `007afb1` yields a tree matching the dev tree (`13118de3…`). The sha256 pin
  in `install.sh`/`install.ps1` updated to `dd7b5f35…`.

# 0.13.2 — 2026-11-22

A review by five independent agents (math, logprobs plumbing, UI, installation/build, tests and
number honesty) found two blockers and fourteen serious defects. This version closes all of them.

**Fixed — numbers**

- Cross-validation folds were cut by rows: 626 rows, 205 unique pairs, and in 88.5% of test rows
  the same answer was in training. Now folds are by `(model, prompt)` — `docs/VALIDATION.md` §17.
  AUROC of the trained weights 0.809 → 0.800, the `digitDensity` contribution +0.046 → +0.014.
- `phi` in `scripts/collect.py` was computed as entropy, while the runtime computes confidence: the `meanPhi` weight
  was trained with the opposite sign. Now both sides compute `1 − H/ln K`; old sets
  are normalised on load in `calibrate.py`.
- `digitDensity` in Python was computed over Unicode digits and code points, in TS — over ASCII and UTF-16.
  Aligned with the TS behaviour.
- `--by-model` gave weights to models with four negatives (AUROC 0.153). The threshold is 30 examples
  of each class, otherwise the bundle has `"weights": null`.
- `normalizedEntropy` normalised entropy by `topK` but computed it over all alternatives.

**Fixed — runtime**

- `OPENCODE_TRUTHPROBE=off/0/false` really turns logprobs off (before, the value fell through
  into the auto-check cache).
- The auto-check cache is addressed by the `provider/model` pair; a verified model no longer enables
  logprobs for the rest of the provider's models.
- `classify` recognises `ok` tokens in any channel (`logprobs.content`, `reasoning_content`), so
  reasoning models are no longer cached as `ignored`.
- `parseLinearWeights` throws on `null` instead of a silent zero; the absence of per-model weights is written
  to stderr once.
- On step abort the confidence of the text already received is not lost, token maps are cleared.

**Fixed — interface**

- The TUI shows `answer confidence … bar · level` always, not only with doubtful sentences.
- desktop restores the level from `score` if the part is old.
- `pct`/`level` in the TUI are robust to `NaN`, sentence trimming is by code points, emoji are not broken.
- `ConfidenceMeter`: a faint track instead of an overlay on top of the fill.

**Fixed — installation and CI**

- `install.sh`: a `git status --porcelain` check before `git reset --hard`; `--dry-run` really
  does not change the tree; the patch is verified by sha256.
- `install.ps1`: a unique temporary file, hash verification, bringing an existing clone to the base.
- `scripts/dev-setup.sh`: idempotency via `apply --reverse --check`, `git am --abort`.
- CI: typecheck `session-ui`, `tui`, `desktop`; protocol tests of the ai layer really run
  (`TRUTHPROBE_REQUIRE_PROTOCOL_TESTS=1`) instead of being skipped.
- `package.json`: `bun test test` instead of a single file.

**Tests**

- 127 truthprobe tests (was 119), 349 asserts: `partial` status, `digitDensity` on non-ASCII,
  `top_logprobs` longer than `topK`, null weights, the reasoning channel in `classify`.
- Two tautological checks removed in `test/score.test.ts`.

# 0.13.1 — 2026-11-21

The demonstration example in the docs is recomputed with the current formula and rewritten the way
the TUI really prints it. The old numbers were taken before §14, and the labels did not match the interface.

**Fixed**

- `README.md`, `README.en.md`, `docs/SMOKE-E2E.md`, `docs/VALIDATION.md` §6: the transcript
  "`first-sentence confidence 71%` / `answer confidence 40% · 1 doubtful sentence` / `! #2 8%`"
  replaced with the measured output of the current build: `first-token confidence 71%`,
  `answer confidence 44% ▰▰░░░ · risky · 1 doubtful sentence`,
  `▌ #2 ▰░░░░ 16% · unreliable: …`. The percentages were taken by running the mock through `scoreAnswer`:
  answer `0.4442 · risky`, sentences `0.9672` and `0.1584`, first token `0.7076`.
- `docs/SMOKE-E2E.md`, `docs/VALIDATION.md`: the part JSON in those sections is recomputed on the same
  tokens (`score 0.4442`, `risk 0.5558`, `level risky`) instead of being left from the old formula.
  A line was added in §6 that before §14 the same tokens gave 40% and 8%.
- `package.json`: the description no longer promises a "first-sentence confidence badge" — now
  "first-token confidence badge, answer confidence line with a level and a meter, doubtful sentences".

# 0.13.0 — 2026-11-20

Reliability on non-Latin text: verified that token alignment does not break, and this is
pinned by a test. Plus two commands that were missing for data reproducibility.

**Added**

- `packages/core/test/truthprobe-unicode.test.ts`: five scenarios — Cyrillic, CJK
  (`北京是中国的首都。`), an emoji flag, `Zürich` with combining marks, Arabic. For each
  it checks that tokens join into the source text, the offsets cover the whole text
  (`lastEnd == text.length`), `status = ok`, `risk = 1 − score`, sentence boundaries match
  `text.slice(start, end)`; separately — CJK segmentation by `。` and the degradation "foreign tokens →
  unavailable". The truthprobe suite now has **119** tests (6 files instead of 5).
- `Makefile`: targets `data` (collecting rows via `scripts/collect.py` with env `COLLECT_URL`,
  `COLLECT_MODELS`, `COLLECT_SAMPLES`) and `weights` (`scripts/calibrate.py --fit --by-model
  --out data/weights.json`).

**Verified by a run**

No alignment code had to change: on all five texts `scoreAnswer` returned `status=ok`,
`score 0.9512` (tokens cut exactly, probabilities equal), sentences were split correctly,
the last offset matched the text length. That is the point of the test: to pin down behaviour
that is already correct, so that a future edit of `alignTokens` does not break it silently.

**Caveat**

The test catches degradation only with a complete mismatch of tokens and text: `alignTokens` looks for
a token in an 8-character window, so a single shared character still yields a match. This is known
behaviour and was deliberately left unchanged.

**Patch**

Nineteen commits, `46 files, +7023/−40`, 431 079 B, `git am` on `007afb1` yields
the same tree byte for byte.

**CI**: run `44787911144` on `92f1c65` — **7 of 7 jobs**: a patch of 19
commits applies on ubuntu and windows, 119 truthprobe tests are green, the installers
apply 19 commits, e2e puts the verdict into the base, the CLI builds. After the repository was recreated (21.11.2026) the first run [`44918215420`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44918215420) on `69b0b4e` also gave **7/7**, and the Contributors API shows only `vladmurnik`.

**Fixed in DX**

- `scripts/build-desktop.sh`: desktop silently packaged the old CLI — electron-builder takes the binary
  from `packages/desktop/resources/opencode-cli[.exe]` (`extraResources`), not from `packages/cli/dist`.
  A staging step (2/4) and a warning in `docs/DEVELOPMENT.md` were added.
- `scripts/build-desktop.sh`: launching from a non-interactive `bash -lc` did not pick up `~/.bun/bin`,
  and the build failed with `error: preload not found "@opentui/solid/preload"`. Now the script itself
  puts `$HOME/.bun/bin` at the front of `PATH`. A full build by the script was verified: `TruthProbe.exe`
  246 624 768 B, `resources/opencode-cli.exe` contains `digitDensity`.

# 0.12.0 — 2026-11-20

The first text feature whose contribution a measurement found: the share of digits in the answer.

**Added**

- `packages/core/src/truthprobe/score.ts`: `digitDensity(text)` — the share of digit characters in the visible
  answer; the value goes into `ScorerFeatures.digitDensity` for the sentence and for the answer.
  It is NOT part of the default score, only of the trained weights.
- `packages/core/src/truthprobe/scorer.ts`: `FEATURE_NAMES` extended with `digitDensity`,
  `LinearWeights.digitDensity` declared optional — weight files without the field are read as 0.
- `scripts/enrich-digits.py`: recomputes the feature in already collected JSONL from the `answer` field
  (idempotent, `--check` only reports discrepancies).
- `scripts/collect.py`, `scripts/calibrate.py`, `scripts/evaluate.py`: compute/read the same
  feature so that the weights apply to the same numbers the runtime saw.

**Measured** (626 rows, 544 truths / 82 ordered lies, out-of-fold, 5 folds):

| feature set | AUROC | ECE |
| --- | --- | --- |
| `exp(meanLp)` (runtime formula) | 0.597 | 0.098 |
| meanLp + minLp + phi + fracLow | 0.774 | 0.282 |
| same + `digitDensity` | **0.809** | 0.274 |

Hedging could not be checked: in truths and lies the share of hedging words is the same and equals 0 —
we call this unverified rather than "does not work". Details — `docs/VALIDATION.md` §15.

**Fixed**

- `packages/core/test/truthprobe-scorer-bundle.test.ts`: the feature fixture did not contain
  `digitDensity`, which made the typecheck of the patched tree fail (7 × TS2741) — the tests
  still passed because the field is optional at runtime. Found by the CI run `44784193788`.
- `scripts/build-desktop.sh`: desktop silently packaged the **old** CLI — electron-builder takes the
  binary from `packages/desktop/resources/opencode-cli[.exe]` (`extraResources`), not from
  `packages/cli/dist`. A staging step was added: the built CLI is copied into `resources` before
  `electron-vite`/`electron-builder`. Verified on the installed build: in
  `resources/opencode-cli.exe` there is `digitDensity` (3 occurrences), in `app.asar` —
  `confidence-meter` and `doubtful-list`.

**Not verified**: the negative set is single and obtained by ordering (the model was asked to lie), so
the +0.034 gain cannot be transferred to spontaneous hallucination. The default formula is the same.

# 0.11.0 — 2026-11-20

The built-in confidence formula is rewritten after measurement: `phi` was inverting the score.

**Changed**

- `packages/core/src/truthprobe/scorer.ts`: `geometricScorer()` is now `clamp01(exp(meanLp))` —
  only the geometric mean of the answer token probabilities. The worst-token term and `phi`
  are removed from the default formula; as features they remain and work in the trained weights.
- `packages/core/src/truthprobe/score.ts`: the same formula in the path without a swappable scorer.
- `packages/core/test/truthprobe-scorer.test.ts`: the formula test updated, a test added for
  "`phi` and the worst token no longer affect the built-in score".
- `scripts/measure-lies.py`: `geometric()` aligned with the runtime, `--variants` added — a comparison
  of fixed formulas without training, so the measurement is reproducible from the repository.

**Measured** (626 rows: 544 truthful, 82 ordered-lies)

| formula | AUROC | ECE | Brier |
| --- | --- | --- | --- |
| previous `0.4·geo + 0.3·worst + 0.3·φ` | 0.388 | 0.368 | 0.292 |
| new `exp(meanLp)` | **0.597** | **0.098** | **0.127** |
| trained weights, out-of-fold | 0.774 | 0.282 | 0.181 |

On 739 fully correct rows (`data/rows-hard.jsonl`) ECE drops from 0.493 to **0.160**,
Brier — from 0.269 to **0.044**: the previous formula systematically understated confidence.

**Not verified**

- Real (not ordered) hallucinations are still not measured: 1 440 requests on four
  banks produced not a single model error. 0.597 is weak separation on one narrow set.
- Level thresholds are not recalibrated for the new scale: the same answers now get a higher
  level, which is expected, but was not separately checked on live sessions.

- CI `44761971781` on `128b5f4`: **7 of 7 jobs success** — the patched tree
  (110 truthprobe tests) on ubuntu and windows, the installers, the e2e verdict, the CLI build.

# 0.10.0 — 2026-11-20

The first measurement on the "lie" class, even if an ordered one, and one inconvenient result.

**Added**

- `scripts/make-liar-bank.py`: a bank where the model is asked to answer incorrectly; the "lie" label is known
  from the task setup, and the logprobs are real. If the model refuses to lie, `--auto-label` returns
  label 1 for the row, and it does not end up in the negatives.
- `scripts/measure-lies.py`: comparison of the built-in `geometric` formula and the trained weights
  (out-of-fold, 5 folds) on one set, `--json`, breakdown by model.
- `data/qa-liar-bank.jsonl`, `data/rows-liar.jsonl`, `data/rows-lie-vs-truth.jsonl`.

**Measured**

- 34 questions × 4 models: 626 rows, 544 truthful, 82 ordered-lies.
- `geometric` AUROC **0.388** (worse than chance), ECE 0.368, Brier 0.292.
- `fitted` (the same 4 features, out-of-fold) AUROC **0.774**, ECE 0.282, Brier 0.181.
- By model: `glm-5.3-flash` 0.863, `deepseek-v4.1-flash` 0.629, `particle` 0.522.

**Observation**

- The cause of the built-in formula's inversion: for ordered lies `phi` is 0.468 versus 0.125 for truths, and
  `phi` enters the formula with weight 0.3. The first token after a strange instruction is less predictable,
  and the formula reads that as "more confident".
- 1 440 requests on four banks produced not a single real negative: the models answer correctly
  or stay silent. That is why the default weights are still `geometric`, and ordered lies are not suitable as
  a basis for retraining.

# 0.9.1 — 2026-11-20

Withdrawal of wrong numbers, a fix for defective labelling and protection against it in the future.

**Withdrawn**

- AUROC `0.538 / 0.683 / 0.866` from section 0.9.0 and the conclusion "logprob features do not catch confident
  lies" — are wrong. All 40 "negatives" were defects in our data: 23 answers to an ambiguous question
  ("Which is the largest planet: Saturn or Neptune?" with the reference `jupiter`, which is not among the options
  — the models answered the question asked correctly) and 17 truncations by `max_tokens 80`.
  After cleaning the set has **739 correct and 0 wrong**, `evaluate.py` prints `AUROC n/a (one class)`.
  The file `data/weights-hard.json` is deleted: there was nothing to train it on.

**Added**

- `scripts/audit-bank.py` — an audit of the question bank against the collected rows: if several different models
  independently converge on an answer that is not in the reference, the item is marked as a bank defect; separately
  it catches "the question offers `X or Y`, while the reference is outside those options". Exits with code 1 on findings.
  On the old bank it found exactly 4 such items.
- `scripts/collect.py`: an answer with `finish_reason == "length"` is marked `truncated`, and `label=0`
  is not set from a truncation — otherwise the weights learn from our greed.

**Fixed**

- `data/qa-hard-bank.jsonl`: 4 questions rewritten without a false choice ("Saturn or Neptune",
  "three or five", "Zurich or Geneva", "Buzz Aldrin or Yuri Gagarin").
- `data/rows-hard.jsonl` and `data/rows-hard-t1.jsonl` rebuilt for the fixed questions
  with `max_tokens 220`; rows with wrong labels removed.

**What remains measured**

- `geometric` on 739 rows: ECE 0.493, Brier 0.269 — the scorer systematically understates confidence.
- The levels `likely / uncertain / risky` give 100% correct on this set: the flag fires on
  correct answers more often than it should.

# 0.9.0 — 2026-11-20

Measurement appeared, and with it the first real negatives: the scorer now has a quality number, not just
a feeling.

**Added**

- `scripts/evaluate.py` — AUROC (with tie averaging), ECE, Brier, the share of correct answers within each
  level; three modes (`geometric` / `global` / `per-model`), `--json`, a `--min-auroc` gate.
  Stdlib only.
- `make eval` on the `data/eval-fixture.jsonl` fixture (96 real rows).
- `scripts/collect.py`: `--samples N` — several samples per (model, prompt) pair, a `sample` field
  in the row, `--resume` skips by `(model, prompt, sample)`.
- `data/qa-hard-bank.jsonl` — 47 tricky but machine-checkable questions.
- `data/rows-hard.jsonl` and `data/rows-hard-t1.jsonl` — 752 rows each (`T=0.8` and `T=1.0`),
  `data/weights-hard.json` — a weights bundle trained on them.
- `packages/tui/src/routes/session/message-parts.tsx`: the `▰▰▰░░` bar with fixed width 5 and the
  level label in the theme's semantic colours; doubtful sentence rows are coloured by level.

**Fixed**

- `scripts/calibrate.py`: `load()` accepted only `true/false`, while `collect.py` writes `1/0` — because of
  that all collected rows were silently discarded and `--fit` never saw both classes.
- `packages/tui`: 4 pre-existing type errors in `level()` (`TruthprobeLevel | null` was not
  coerced to `string | undefined`).

**Measured** (720 rows: 700 correct, 20 wrong)

| mode | AUROC | ECE | Brier |
| --- | --- | --- | --- |
| `geometric` | 0.538 | 0.470 | 0.272 |
| `global` weights | 0.683 | 0.437 | 0.227 |
| `per-model` weights | 0.866 | 0.285 | 0.161 |

Out-of-fold AUROC by model: `glm-5.3-flash` 0.964, `particle` 0.791, `deepseek-v4.1-flash` 0.726,
`deepseek-v4-flash` 0.612.

**Not verified**

- 23 of the 40 negatives are the same question, so 0.866 cannot be read as detector quality.
- Confident lies are indistinguishable from confident truths by logprobs: the wrong answer "Saturn" has the same
  low entropies as correct ones. Logprob features catch hedging, not confident fabrication.
- The AUROC CI gate is not enabled: on such a set it would give noise instead of protection.

# 0.8.0 — 2026-11-20

The confidence verdict became visible to the eye, not just a number in the meta line.

**Added**

- `packages/session-ui/src/message/confidence.tsx` — a shared component for desktop:
  `ConfidenceMeter` (a 4px bar with a fill by percentage and a level colour),
  `ConfidenceLine` (level dot + "confidence NN% · level" + bar; with
  `status: unavailable` — a "no confidence signal" chip with the cause in `title`),
  `DoubtfulList` (a list of doubtful sentences: the "#N NN% level" flag + text,
  a left border and a backdrop in the level colour, `data-slot` for tests and styles).
- `packages/session-ui/src/message/message-content.tsx` — the
  `data-slot="text-part-doubtful"` block now renders `ConfidenceLine` + `DoubtfulList`
  instead of a scattering of `span`s; the dead `doubtful` and `answerConfidence` memos are removed.

**Verified**

- `bun check --no-script -b` in `packages/session-ui`: "No type errors in 383 files".
- `bun test src/message/doubtful.test.ts`: 8 pass / 0 fail.
- `cd packages/core && bun test test/truthprobe`: **109 pass / 0 fail**.
- Patch: **15 commits**, `45 files, +6875/−40`, 406 664 B, `git am` on `007afb1`
  yields the same tree byte for byte (`WT_TREE == DEV_TREE`, 0 differences).
- CI `44736706708`:
  **7 of 7 jobs success** on hosted ubuntu-latest and windows-latest, including `cli build`.
- Desktop rebuilt and installed: `TruthProbe.exe` 246 624 768 B, build 15:39,
  `app.asar` contains `confidence-meter` and `doubtful-list` — the new verdict is in the build.

# 0.7.0 — 2026-11-20

Calibration weights now work per model, not "for all at once", and there is something to collect them with.

**Added**

- `packages/core/src/truthprobe/scorer.ts`: `WeightsBundle`, `parseWeightsBundle`,
  `bundleScorer`, `weightsFor`. The `{global, models}` bundle from `calibrate.py --fit --by-model`
  is read as is; `TRUTHPROBE_SCORER=linear:<file>` selects the weights by
  `providerID/modelID` with a fallback to `global`. A flat weights JSON is still accepted.
- `packages/core/src/truthprobe/score.ts`: `scoreAnswer(..., model?)` — the fourth argument
  `providerID/modelID`, which goes into `ScorerInput.model`.
- `packages/core/src/session/runner/publish-llm-event.ts`: `modelKey` from `input.model`
  is passed to both the regular and the reasoning scoring path.
- `scripts/collect.py`: collection of calibration rows over a list of models and prompts
  (`--models`, `--prompts`, `--out`, `--resume`, `--dry-run`, `--limit`). Features
  are computed exactly as in the runtime: `phi` — the entropy of the first token's `top_logprobs`,
  `fracLow` — the share of `logprob < ln 0.5`.
- `packages/core/test/truthprobe-scorer-bundle.test.ts`: 12 tests for bundle parsing,
  weight selection, fallback to `global` and to geometric on a broken file.

**Fixed**

- `scripts/probe-freellmapi.py`: `fracLow` was computed by the `−1.0` threshold, while the runtime uses
  `ln 0.5`; `phi` was the `minLp/meanLp` ratio, not entropy. Both metrics are aligned
  with the runtime, otherwise the collected set would not correspond to the scorer's numbers.

**Verified**

- `bun test test/truthprobe` in `packages/core`: **109 pass, 0 fail** (5 files); typecheck
  schema/ai/core/client green; the repository `bun test test` — **90 pass / 8 skip / 0 fail**.
- A live run on the mock: the same answer gets `0.99966 · safe` when the bundle contains
  weights for `mock/mock-1`, and `0.000335 · unreliable` when only `other/model` has weights.
- CI `44736706708`:
  **7 of 7 jobs success** on hosted ubuntu-latest and windows-latest.
- Patch regenerated (`28 commits`, 342 760 B) and verified by `git am` on `007afb1`: the tree
  matches the dev branch byte for byte.

**Not verified**

- Calibration on real labelled data: a set of 200–500 rows with `label` is needed. `collect.py`
  is ready for that, but there are no FreeLLMAPI provider keys — all 25 models are `enabled: false`.

# 0.6.3 — 2026-11-20

An external data source for calibration: FreeLLMAPI.

**Added**

- `scripts/probe-freellmapi.py`: checks whether the endpoint returns `logprobs`, and writes
  a measurement row (`meanLp`, `minLp`, `phi`, `fracLow`) into JSONL. If there are no tokens, it
  prints the verdict "the model is not suitable" instead of silence.
- `scripts/calibrate.py --fit --by-model`: separate scorer weights per model
  (grouping by the `model` field), out-of-fold AUROC/ECE by group, a bundle
  `{version, features, global, models}`. The runtime takes `global`; per-model selection is not
  implemented and is named as an open item.
- `docs/FREELLMAPI.md`: how to bring the router up in Docker, where to get a unified key, how to
  connect it as a provider in opencode, what is measured and what is not.

**Verified**

- The FreeLLMAPI image comes up (`healthy`, 25 models seeded, API login works).
- `probe-freellmapi.py` run against a live log-likelihood source `freepi/particle`:
  22 tokens with logprob, `meanLp -0.0573`, `minLp -0.4930`.
- `calibrate.py --demo --fit --by-model` builds a bundle without errors.

**Not verified**

- End-to-end inference through FreeLLMAPI: provider keys are needed, and there are none.
  Passing `logprobs` through the router is also an open question per model.

# 0.6.2 — 2026-11-19

The patch was verified on someone else's clean machines.

**Added**

- `.github/workflows/verify.yml`: GitHub Actions on hosted runners `ubuntu-latest` and `windows-latest`.
  Matrix: `patched tree` (clone opencode at `007afb1` → `git am` → `bun install` → typecheck of four
  packages → truthprobe tests), `installer dry-run` (both installers), `repo tests`, `end-to-end verdict`
  through a mock provider with logprobs, `cli build`.
- Run `44593481931`:
  **all 7 jobs success**.

**Fixed**

- The patch was regenerated after fixing 7 type errors that only surfaced during typecheck of the
  patched tree (`packages/schema`, `packages/core`: `Level` → type alias, `Required<Omit<…>>`,
  weight guards in the scorer, `level` in the reasoning fallback, level comparison via `String(...)`).
  Now `git am` of the patch yields the same tree as the dev branch, byte for byte, and it passes typecheck.

# 0.6.1 — 2026-11-19

Found by running the full monorepo test suite (7 713 tests), not by eye.

**Fixed**

- `packages/schema/src/truthprobe.ts`: `level` accepted only a value from the five levels or `undefined`,
  but `scoreAnswer` puts `null` when there is no signal. Because of this, parts with the `unavailable` verdict
  failed on decoding (`Expected Truthprobe.Level | undefined`), and in the full run this produced
  **218 failures** in foreign suites (`SessionRunnerLLM` and neighbours). Now the schema is `optional(NullOr(Level))`,
  and the client types also allow `null`. After the fix: 218 → 62 failures, and all 62 are network/spawn
  tests unrelated to the patch.
- `packages/client/src/promise/generated/types.ts`: `level?: TruthprobeLevel | null`.

**Documentation**

- README (ru/en): a "What is actually verified" section with measurements, test numbers and an honest list of what
  was not verified (clean VMs, Linux/macOS, cloud providers, calibration).

# 0.6.0 — 2026-11-19

The scorer became swappable, installation — a single script with flags.

**Added**

- `packages/core/src/truthprobe/scorer.ts`: the `Scorer` interface, the built-in `geometric` and
  `linear:<weights.json>` — `score = sigmoid(bias + w·[meanLp, minLp, meanPhi, fracLow])`.
  Loading via `TRUTHPROBE_SCORER`; a broken file or a non-numeric weight does not break scoring — one
  warning and a fallback to the built-in formula.
- `scripts/calibrate.py --fit [--out FILE]`: logistic regression with class balancing,
  AUROC/ECE on out-of-fold predictions, a ready weights JSON.
- `install.sh` / `install.ps1`: flags `--dir`, `--dry-run`, `--uninstall`, `--scorer`,
  a `git apply --check` before applying and printing the launch command.
- `docs/MODEL-SUPPORT.md`: which models return logprobs, how to check your own.
- `scripts/probe-logprobs.py --md`: a Markdown table from the probe result.

**Fixed**

- The installer no longer leaves the tree half-patched: first `--check`, then `am`/`apply`.

# 0.5.0 — 2026-11-19

Confidence became readable: next to the percentage there is a level, doubtful sentences are highlighted
with a flag, not just with text colour.

**Added**

- The level scale `safe` / `likely` / `uncertain` / `risky` / `unreliable`
  (`packages/core/src/truthprobe/levels.ts`). The level is computed in the core and travels in the part next to
  `score`, so session-ui, the TUI and REST show the same thing.
- The answer line: `answer confidence 71% · uncertain`; the meta badge: `answer 71% uncertain`.
- Risk thresholds can be shifted by the environment: `TRUTHPROBE_RISKY_THRESHOLD`, `TRUTHPROBE_SHAKY_THRESHOLD`
  (0..1; an invalid value is ignored, the numbers do not break).
- `no confidence signal` instead of `confidence unavailable`: the text states plainly that the provider did not
  send token probabilities, and gives the cause.

**Fixed**

- Doubtful sentences are no longer "invisible": instead of text colour — a flag with a left border and a background
  (amber for `risky`, red for `unreliable`), works in light and dark themes. In the TUI —
  the `▌` marker and colour by level.
- The "token drift" test is aligned with the actual behaviour: mismatched tokens give
  `unavailable` with the cause `tokens do not match the answer text`, not an invented `partial`.

# 0.4.0 — 2026-11-19

Confidence numbers are finally visible on real gateways: free-pi (`particle`, `deepseek-*`) sends
logprobs in a separate chunk without text, and the old code lost them.

**Fixed**

- The protocol no longer discards logprobs that arrive in a chunk with an empty delta: tokens
  accumulate in the parser state and travel in the `providerMetadata` of the next text delta, and the remainder —
  in the closing event. That was the cause of "no numbers" on particle and deepseek.
- The part gets a verdict **always**, even when there are no tokens: `status: "unavailable"` with a cause instead of
  an empty space. The UI now speaks up instead of staying silent.
- Confidence from reasoning tokens is substituted into the answer when the visible text arrived without logprobs
  (`reason: "confidence from reasoning tokens"`).
- Tokens are matched against the text (`alignTokens`), so internal tokens like `<​/think>` no longer
  shift sentence boundaries: `status: "ok"` and non-empty `sentences` on live answers.
- The provider probe requests the same `top_logprobs: 20` as the production request.
- `OPENCODE_TRUTHPROBE=off` disables the feature before the cache is read, as promised.
- A single CJK/kana/hangul character counts as a content token.
- `first-token confidence` is named for what it measures (it used to say "first sentence").
- In desktop and the TUI the `answer confidence` line is shown even without flags, with a cause at `unavailable`.
- `GET /api/info` answers in any service state — because of this desktop exited on a timeout.
- `install.sh` switches an existing checkout to `BASE` and checks the patch via `git apply --check`
  before applying.

**Honestly**

- The `0.45` threshold and the `0.4/0.3/0.3` weights are still not calibrated on a labelled set:
  AUROC is not measured, `docs/CALIBRATION.md` describes the protocol but not the result. Read the percentages as
  "how smoothly the model went through this text", not as the probability of truth.

# 0.3.2 — 2026-11-19

The desktop application can be installed separately from opencode: its own name, its own data directory, without someone
else's auto-update.

**Added**

- `OPENCODE_DESKTOP_APP` and `OPENCODE_DESKTOP_APP_ID` at build time set the application name, AppUserModelID,
  the `userData` directory, the installer name and the window title. The values are baked into the bundle through
  `electron.vite.config.ts`, so there is no need to patch the ready `out/main/index.js`.
- The window and tab title is no longer the literal `OpenCode`: it comes from `packages/app/src/brand.ts`
  (Electron takes the title from `document.title`, not from the `BrowserWindow` option).
- An application built this way does not write `app-update.yml` — opencode auto-update will not overwrite it.

**Verified**

- Building `TruthProbe` from the `feat/truthprobe` tree: `dist/win-unpacked/TruthProbe.exe`,
  `resources/opencode-cli.exe` (our patched CLI), `app-update.yml` absent.
- Launch: 5 `TruthProbe` processes + 1 `opencode-cli`, window title `TruthProbe`,
  data in `%APPDATA%\ai.truthprobe.desktop`.
- Typecheck: app (2 445 files), desktop (3 569, 2 projects) — 0 errors.
- Patch: 37 files, +2139/−34, 3 292 lines, seven commits on top of `007afb1`.

# 0.3.1 — 2026-11-19

Doubtful sentences are visible in the desktop application too, not only in the terminal.

**Added**

- The list `! #N NN%: <start of sentence>` under the answer in `@opencode/session-ui` — the same markup
  the TUI prints, so desktop and web show the same thing. The mapping logic is moved out into
  `packages/session-ui/src/message/doubtful.ts` and covered by 6 tests (`doubtful.test.ts`): the percentage,
  filtering by `flag`, numbering from one, trimming to 96 characters, broken fields do not break the render.

**Updated**

- Patch: **29 files, +2084/−27, 3 080 lines, six commits** on top of `007afb1`.
- session-ui typecheck — 382 files (was 380).

# 0.3.0 — 2026-11-19

Autopilot: keys and providers are checked by themselves. The confidence badge works both in the terminal and in the
desktop application.

**Added**

- The core plugin `opencode.truthprobe` listens to `http.request`, where both the model and the authorised
  URL are visible, and sends one test request (`"ping"`, `max_tokens: 1`, `logprobs: true`,
  `top_logprobs: 3`). The hook only puts the event into a queue — the check runs in a separate fiber,
  so the model's answer does not wait for it.
- A verdict cache `<data>/truthprobe/capabilities.json`: `ok`/`ignored`/`rejected`/`unsupported` — 7 days,
  `auth` — an hour, `error` (429/5xx/network) — not cached.
- Auto-enabling: the core passes the cache path to the `ai` package via `OPENCODE_TRUTHPROBE_CACHE`,
  `truthprobeEnabled` reads it itself (fallback — the standard data directory). Environment
  variables are no longer needed.
- logprobs support is treated as a provider property: a fresh `ok` record for any model of that
  provider enables collection, so aliases and variants do not suppress the badge.
- `OPENCODE_TRUTHPROBE_PROBE=off` disables only the auto-check.
- Desktop: a `confidence NN%` chip (and `· partial`, `· N doubtful`) in the answer footer through
  `@opencode/session-ui`; the same component draws the web interface too. The field is passed through from
  `timeline-next/tools/assistant-content.tsx` and `message/current-message.tsx`.
- Installers in two commands: `install.sh` (Linux/macOS) and `install.ps1` (Windows) — fetch
  `sst/opencode` at `007afb1`, apply the patch, install dependencies, print the version.
- `README.en.md` — a full English README with a language switcher.
- 32 unit tests for the auto-check logic (`packages/core/test/truthprobe-capability.test.ts`).

**Fixed**

- `Model.mergeCapabilities` lost `logprobs`: `capabilities.logprobs` from the config did not reach the
  model. Now it is passed through.

**Verified**

- A mock provider, two runs in a row without environment variables: RUN1 — the probe goes out, the cache gets
  `{"status":"ok"}`; RUN2 — **2 of 2** streaming requests with `logprobs: true, top_logprobs: 20`,
  no new probes. A `truthprobe` with status `ok` sits in `session_part`.
- Typecheck: ai (357+322 files) and core (2 030 files), session-ui (380), app (2 443),
  desktop (3 567, 2 projects), tui (1 942) — 0 errors.
- The patch on a clean tree (as of 0.3.0): 27 files, +1961/−27, 2895 lines, applies via `git am`
  without conflicts. In 0.3.1 the doubtful sentence list was added to it.

# 0.2.0 — 2026-11-19

Verifiability and packaging.

**Tests**

- 45 unit tests for scoring and segmentation (`packages/core/test/truthprobe.test.ts`).
- 8 OpenAI protocol tests (`packages/ai/test/truthprobe.test.ts`): the capabilities/`OPENCODE_TRUTHPROBE` gate,
  the request field composition, parsing of `choices[i].logprobs → providerMetadata`.
- Full runs: core 7 661 tests, ai 2 305, schema 95; typecheck schema/ai/core/client/tui.

**Fixed**

- A token that starts with a space at a sentence boundary is no longer lost:
  the match is computed by the intersection of ranges, not by the start offset.
- CJK sentences (`。！？`) are split without a mandatory space after the terminator.
- An abbreviation no longer glues sentences together if the next word starts with a capital letter
  (`etc. And more.` → two sentences).

**Added**

- Export of `truthprobeBody` / `truthprobeEnabled` / `truthprobeFromDelta` for tests.
- A Windows build: `dist/opencode-truthprobe-windows-x64.exe` (233 MB) verified on a live mock.
- `scripts/install-cross-deps.py` — installs win32 optional dependencies for cross-building from Linux.
- GitHub plumbing: CI, licence, contributing, `scripts/build-*.sh`.

# 0.1.0 — 2026-11-18

The first working patch.

- The `Truthprobe.Info` schema, the `truthprobe` field in `session.text.ended` and in `AssistantText`.
- The request `logprobs: true, top_logprobs: 20` for models with `capabilities.logprobs` or with `OPENCODE_TRUTHPROBE=1`.
- Scoring on the first token (normalised entropy), on the sentence and on the whole answer.
- TUI: a badge before the answer, a confidence block with the numbers of doubtful sentences after the answer.
- An end-to-end run on a mock provider, live rendering in a pty, a build into a single binary.
