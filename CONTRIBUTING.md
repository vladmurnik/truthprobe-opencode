> Русская версия: [docs/ru/CONTRIBUTING.md](docs/ru/CONTRIBUTING.md)

# How to make a change

TruthProbe is a patch on top of [sst/opencode](https://github.com/sst/opencode), not a fork.
The edits live in the patched tree, `patches/truthprobe-0001.patch` is rebuilt from it,
and it is this file that is the result of the repository.

## Quick start

```bash
git clone https://github.com/vladmurnik/truthprobe-opencode
cd truthprobe-opencode
make setup          # clone of opencode at BASE, git am of the patch, bun install, tests
make test           # unit tests of the repository itself (~2 s, without cloning)
make preview        # mock provider + one request through the CLI, the verdict is visible
make data           # collect new calibration rows (an OpenAI-compatible gateway is needed)
make weights        # train the weights on the collected rows → data/weights.json
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-setup.ps1
```

Required: `git`, [`bun`](https://bun.sh) ≥ 1.2, `python3` (for the mock provider and the scripts).
Docker is needed only for FreeLLMAPI — see `docs/FREELLMAPI.md`.

## The change cycle

1. **`make setup`** — `.worktree/opencode` appears with the patch applied.
2. You edit the code there (the file map is `docs/DEVELOPMENT.md`).
3. **`make test`** — the tests of the repository; in the tree: `bun test test/truthprobe`.
4. Commit in `.worktree/opencode` (one commit = one thought, the message in the `feat(truthprobe): …` style).
5. **`make patch`** — rebuilds `patches/truthprobe-0001.patch` from `BASE..HEAD`.
6. **`make verify`** — tests + a check that the patch applies to a clean base.
7. Commit in this repository: the patch + (if they changed) the reference copies in `src/truthprobe/`,
   the tests in `test/`, the documentation.

`BASE` is the sst/opencode commit the patch is cut against (`007afb1b…`). It can be changed,
but then the patch must be regenerated and `make verify` run on the new base.

## Rules that are not up for discussion here

- **Only measured numbers.** Any figure in the README/docs must have the command by which it was obtained.
  Not measured — so we write exactly that: "not verified", with the reason.
- **No invented metrics.** `AUROC`/`ECE` on synthetics — a property of the synthetics; label that explicitly.
- **Degradation instead of a crash.** No `logprobs`, a broken weights file, someone else's model — the scorer falls back
  to geometric and prints one warning, but does not break the session.
- **Tests for behaviour, not implementation.** We check "a bad answer gets a lower score",
  not "the function was called twice".
- **The patch stays `git am`-compatible**: commits only, no merge commits and no binaries.

## Before a pull request

```bash
make verify                       # tests + the patch applies to a clean base
bun test test                     # the same run as in CI (the "repo tests" job)
```

If you changed the scorer's maths — attach a couple of "before/after" lines on fixed
tokens in the PR description: it is cheaper than later hunting for why the percentages changed.

## Language

Everything in this repository is written in English: code comments, user-facing strings,
commit messages, documentation. Russian exists as an optional translation — `README.ru.md`
and `docs/ru/*` — and a Russian copy must be updated together with the English original
it mirrors.

The only place where both languages meet inside one file is the banner at the top:
`> Русская версия: …` in the English file, `> English version: …` in the Russian one.

One intentional exception: `scripts/collect.py` keeps a Cyrillic range inside a tokenizer
regex (`[a-zа-я0-9]+`), because the reference answers it splits are Russian. That is code,
not text.

## Where to ask

- `docs/DEVELOPMENT.md` — the "what to change where" map.
- `docs/VALIDATION.md` — what and how was measured, including the CI runs.
- `docs/FREELLMAPI.md` — collecting calibration data on many models.
