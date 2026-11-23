> Русская версия: [docs/ru/DEVELOPMENT.md](ru/DEVELOPMENT.md)

# Development: the "what to change where" map

TruthProbe lives in the patched tree `.worktree/opencode` (created by `make setup`).
The paths below are relative to the root of **this tree**, i.e. `packages/…`. Links to the original
sst/opencode files from `docs/DEVELOPMENT.md` are given so that they are visible even without the tree.

## Data flow (where to look first)

```
provider stream ─► packages/ai/… (request logprobs, parse tokens)
       │                logprobs from the response
       ▼
session/runner/publish-llm-event.ts   ─ accumulates tokens, calls scoreAnswer at the end
       │    modelKey = providerID/modelID
       ▼
packages/core/src/truthprobe/score.ts ─ scoreAnswer(): token alignment, splitting
       │                                  into sentences, features → Scorer
       ▼
packages/core/src/truthprobe/scorer.ts ─ geometric (default) or linear weights
       │                                  from TRUTHPROBE_SCORER, chosen by model
       ▼
schema/src/truthprobe.ts ─ serializes the result (AnswerScore) to the database/client
       ▼
packages/session-ui/src/message/… ─ desktop chip "confidence NN%" and doubtful sentences
packages/tui/src/routes/session/message-parts.tsx ─ the same in the terminal UI
```

The verdict signature (`AnswerScore`): `status`, `score`, `risk`, `level`, `first`,
`sentences[] {i,start,end,text,score,risk,meanLp,minLp,phi,tokens,flag,level}`, `flagged`.

## Maths (core packages)

| File | What is inside | When to touch |
|---|---|---|
| `src/truthprobe/types.ts` | `TokenLogprob`, `ScorerInput{features,text,model}`, `LinearWeights`, `ScoreOptions`, `SentenceScore`, `AnswerScore`, `DEFAULT_SCORE_OPTIONS` | the scorer/schema contract changes |
| `src/truthprobe/score.ts` | `phi()` (1 − normalized entropy of top_logprobs), `alignTokens`, `splitSentences`, `scoreAnswer(text, tokens, options, model)` | the confidence formula, splitting, features |
| `src/truthprobe/scorer.ts` | `geometricScorer`, `linearScorer`, `parseLinearWeights`, `WeightsBundle`, `parseWeightsBundle`, `bundleScorer`, `weightsFor`, `scorerFromEnv()` | interchangeable weights, selection of `models[providerID/modelID]`, fallbacks |
| `src/truthprobe/levels.ts` | `LEVEL_BOUNDS` (safe 0.90, likely 0.75, uncertain 0.55, risky 0.35), `levelOf` | level thresholds |
| `src/truthprobe/sentences.ts` | `splitSentences` (honest splitting into sentences) | text tokenization |
| `src/truthprobe/capability.ts` | the model's ability to return `logprobs` | auto-enabling the probe |

**Important:** `src/truthprobe/*` in this repository are reference copies for tests without a clone.
After editing in the dev tree they must be synchronized (see below). The repository tests are in `test/`.

## Scorer features (must match everywhere!)

| Feature | Definition | Where it is computed |
|---|---|---|
| `meanLp` | mean logprob over the content-bearing tokens of the answer | `score.ts` |
| `minLp` | worst logprob | `score.ts` |
| `phi` | 1 − normalized entropy over `top_logprobs` of the **first** token | `score.ts` `phi()` |
| `fracLow` | share of tokens with `logprob < ln 0.5` | `score.ts` |
| `digitDensity` | share of digits among the characters of the visible answer | `score.ts` `digitDensity()` |

These same formulas must be in `scripts/collect.py` and `scripts/calibrate.py`, otherwise the trained
weights are applied to other numbers and the calibration falls apart. The features are repeated there
as a comment-reference to `score.ts`.

## Calibration scripts (repository, outside the patch)

| File | Role |
|---|---|
| `scripts/collect.py` | collects rows by models and prompts, `--auto-label` against the bank `{prompt, expect}`, cuts out reasoning tokens |
| `scripts/calibrate.py` | `--fit` (linear weights), `--fit --by-model` (the bundle `{global, models}`), AUROC/ECE, refusal on single-class data |
| `scripts/probe-freellmapi.py` | checks that the endpoint returns `logprobs` |
| `scripts/mock-openai-logprobs.py` | a mock provider with real logprobs (for e2e and `make preview`) |
| `scripts/preview.sh` / `dev-setup.sh` / `dev-setup.ps1` / `make-patch.sh` / `build-desktop.sh` / `install-desktop.sh` | DX plumbing |
| `data/qa-bank.jsonl` | canonical answers for auto-labelling (`expect`) |

## How to change a specific thing

### Level threshold (for example `safe: 0.90 → 0.93`)
1. `src/truthprobe/levels.ts` → `LEVEL_BOUNDS.safe`.
2. `packages/core/test/truthprobe-levels.test.ts` (in the tree) — boundary tests.
3. `make patch`, `make verify` (inside — `make docs-check`), update the numbers in README/docs.

### Add a feature to the scorer
1. `src/truthprobe/scorer.ts`: `FEATURE_NAMES` + `LinearWeights` in `types.ts`.
2. `src/truthprobe/score.ts`: compute it and put it into `ScorerFeatures`.
3. `scripts/calibrate.py`: `COLUMNS`, `fit()` (the vector), `--by-model`.
4. `scripts/collect.py`: `features()`.
5. Tests for bundle parsing and fallbacks: `truthprobe-scorer-bundle.test.ts`.
6. Patch, verify, documentation.

### Weights only for `freepi/particle`
```bash
python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --model freepi/particle \
    --prompts data/prompts-labeled.jsonl --out data/rows.jsonl
# set label 0/1, then:
python3 scripts/calibrate.py data/rows.jsonl --fit --by-model --out data/weights.json
TRUTHPROBE_SCORER=linear:data/weights.json bun run --cwd .worktree/opencode/packages/cli src/index.ts run "…"
```
The runtime takes `models[providerID/modelID]` and falls back to `global`. A broken model record
is silently skipped.

### UI (desktop chip and doubtful sentences)
- `packages/session-ui/src/message/confidence.tsx` — a new shared component: `ConfidenceMeter`
  (the scale), `ConfidenceLine` (the line "confidence NN% · level"), `DoubtfulList` (the list of
  sentences with the flag "#N NN% level").
- `packages/session-ui/src/message/message-content.tsx` — the insertion point of `<ConfidenceLine/>` +
  `<DoubtfulList/>` (the block `data-slot="text-part-doubtful"`), plus the memo `confidence()` for the
  meta line (first-token NN% / answer NN% / N doubtful).
- `packages/session-ui/src/message/doubtful.ts` — helpers: `levelOfInfo(probe)`,
  `levelOfSentence(item)`, `doubtfulSentences(probe)`, `percentOf`.
- `packages/tui/src/routes/session/message-parts.tsx` — the same verdict in the TUI.

Typecheck of the package — from the root of the opencode tree: `bun run --cwd packages/session-ui typecheck`
(the same call as in CI; for the TUI — `bun run --cwd packages/tui typecheck`).

### Prompt / collection prompts
The prompts file: txt (one per line) or JSONL `{"prompt": "...", "label": 0/1}`. Pairs
`(model, prompt)` in `--out` are skipped under `--resume`. The bank for `--auto-label`:
`{"prompt": "...", "expect": ["canberra", "two", "2"]}` — short references are compared by
a word-boundary regex, long ones — by substring.

## Environment and variables

| Variable | Where it is read | Purpose |
|---|---|---|
| `OPENCODE_TRUTHPROBE=1` | ai-provider, auto-enabling | turns on collection of logprobs (usually not needed, capability decides) |
| `TRUTHPROBE_SCORER=linear:<path>` | `scorer.ts`, `score.ts` | path to the weights; empty/`geometric` = built-in |
| `TRUTHPROBE_BASE` | `Makefile`, `dev-setup.*`, `make-patch.sh` | the sst/opencode commit under the patch (default `007afb1b`) |
| `TP_DIR` / `OPENCODE_REPO` | `Makefile`, `preview.sh`, `build-desktop.sh` | where the dev tree is deployed |
| `MOCK_PORT` / `COLLECT_URL` | `preview.sh`, `collect.py` | the address of the mock/target endpoint |

An example `.env.example` in the repository root.

## How to know that nothing broke

```bash
make verify                        # repo tests + the patch on a clean base
cd .worktree/opencode
bun test truthprobe                # unit tests of the patch (129 at the moment)
```
(a real run — `make preview`; look at the verdict in `scripts/inspect-db.py` or
`make preview` will print it itself.)

## Before building the patch

1. A commit in the dev tree (no uncommitted changes — `make-patch.sh` will refuse).
2. `make patch` → `patches/truthprobe-0001.patch`.
3. Synchronize the reference copies `src/truthprobe/*` (otherwise `make test` will check stale code).
4. `make verify`.
5. Desktop: `bash scripts/build-desktop.sh --win` (the result is in `packages/desktop/dist/win-unpacked`),
   then `make desktop-install` (`scripts/install-desktop.sh`) — copies the build over
   `AppData/Local/Programs/TruthProbe` and **cleans the CLI cache**.
   The script itself copies the built CLI into `packages/desktop/resources/opencode-cli[.exe]` — it is
   from there that electron-builder takes the binary (`extraResources`). If this step is skipped, the application
   will be built with the **old** CLI and will silently behave like the previous version.
   The stamp `resources/opencode-cli.version` is composed as `<build version>+<sha256[:12]>`:
   the application caches the CLI by this string (`%APPDATA%\ai.truthprobe.desktop\cli\<stamp>-x64`)
   and reuses it as long as the string has not changed. Without a content fingerprint the new build
   does not reach the user — that is exactly what happened on 22.11.2026, when the cache kept serving the CLI from the 19th.

## Signing

The application is built unsigned: `electron-builder` signs only when a
certificate is set. Without it Windows shows "unknown publisher" in the file properties, and SmartScreen
blocks the first launch for every new user — this is the only thing the build lacks
for distribution.

**Build a signed build.** `electron-builder` reads the certificate from the environment:

```bash
WIN_CSC_LINK=/secure/truthprobe.pfx \
WIN_CSC_KEY_PASSWORD='<password>' \
OPENCODE_REPO=$HOME/src/opencode bash scripts/build-desktop.sh --win
```

`WIN_CSC_LINK` accepts a path to a `.pfx` or an HTTPS link; `WIN_CSC_KEY_PASSWORD` — the password for it.
`scripts/build-desktop.sh` prints the signing state at the end: if the certificate is not set, it plainly
writes `WARNING: WIN_CSC_LINK is not set - <path> is unsigned (NotSigned)`, rather than pretending the build
is ready for distribution.

**Verify the result** (Windows, the same file through `\\wsl$`):

```powershell
$exe = "\\wsl$\Ubuntu\home\adik\src\opencode\packages\desktop\dist\win-unpacked\TruthProbe.exe"
(Get-AuthenticodeSignature $exe).Status      # Valid is expected
(Get-Item $exe).VersionInfo | Select-Object ProductName, CompanyName, FileVersion, LegalCopyright
```

**exe metadata** (`Get-Item … .VersionInfo`, measurement 23.11.2026):

| Field | Up to 0.13.15 | Since 0.13.15 |
| --- | --- | --- |
| `ProductName` | `TruthProbe` | `TruthProbe` |
| `FileDescription` | `TruthProbe` | `TruthProbe` |
| `CompanyName` | `OpenCode` | `TruthProbe` |
| `FileVersion` | `2.3.0` (shell version) | `0.13.14` (product version) |
| `LegalCopyright` | `Copyright c 2026 OpenCode` | `Copyright c 2026 TruthProbe` |
| `Signature` | `NotSigned` | `NotSigned` |

`CompanyName` is taken from `extraMetadata.author.name`, `LegalCopyright` — from `copyright`, both fields
`brand()` in `packages/desktop/electron-builder.config.ts` fills from `OPENCODE_DESKTOP_COMPANY`
(by default — `OPENCODE_DESKTOP_APP`). `FileVersion` — `OPENCODE_VERSION`, which
`scripts/build-desktop.sh` reads from `package.json` of this repository: otherwise the exe reports the version of the
shell (2.3.0), while the release tag is a completely different number.

**What this does not prove.** The signature was verified only as "there is no certificate — and that is said out loud";
the build was never run with a real `.pfx`. Launching a signed exe on a clean machine and the SmartScreen scenario
are also not verified.

## Release

A release is a tag plus an attached patch. The `scripts/release.sh` script does this with one command:

```bash
bash scripts/release.sh --dry-run        # show the plan: tag, sum, owner/repo, description
GITHUB_TOKEN=... bash scripts/release.sh # create a draft, upload the patch, publish
make release TAG=v0.13.15                # the same through make
```

What it checks before the network: the tag exists locally, `patches/truthprobe-0001.patch` is in place,
its sha256 matches the pin `PATCH_SHA256` in `install.sh`, `owner/repo` is parsed from
`git remote get-url origin`. The release description is taken from the entry for this tag in `CHANGELOG.md` —
no separate text is needed; if there is no entry for the tag, the script will take the top one and warn.
A repeated run for the same tag updates the description and re-uploads the asset instead of failing.

**What this does not prove.** The script has never been executed with a real token: in the sandbox there is no
token, only `--dry-run` and the negative branches were checked (no tag, sum mismatch).

**If `curl` on this machine does not get through.** In WSL requests to `api.github.com` were breaking with
`curl: (56) Proxy CONNECT aborted` (code `000`), although from Windows the same address answers `200`.
The workaround route — repeat the plan in PowerShell: create a draft release, upload the asset through
`https://uploads.github.com/.../assets?name=truthprobe-0001.patch`, remove `draft`. Take the description
from the entry for this tag in `CHANGELOG.md`, verify the asset sum against `PATCH_SHA256` before uploading — GitHub
returns its own `digest: sha256:…` in the response, and it must match.
