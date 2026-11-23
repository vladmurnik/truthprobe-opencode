> Русская версия: [docs/ru/BUILD.md](ru/BUILD.md)

# Building binaries

The regular opencode build compiles everything into a single executable (`--single`), and the patch
survives that without changes: `truthprobe` reaches the database and the TUI the same way as in
`bun run src/index.ts`.

## Linux x64

```bash
OPENCODE_REPO=~/src/opencode bash scripts/build-linux.sh
# → dist/opencode-truthprobe-linux-x64
```

The manual equivalent:

```bash
cd packages/cli
OPENCODE_TARGET=linux-x64 OPENCODE_RELEASE=1 \
  bun run script/build.ts --single --skip-install --skip-web-ui
```

Verified: **216 MB**, ~13 s, the binary answers on the mock provider and writes `truthprobe` to the database.

## Windows x64

```bash
OPENCODE_REPO=~/src/opencode bash scripts/build-windows.sh
# → dist/opencode-truthprobe-windows-x64.exe
```

Verified: **233 MB**, `sha256 396be271b40c96da602d208df35d27ec947b4716aa4b29de7a5afc9a15b1eb8d`
(the full sum of the build on which the numbers were taken; the binary itself is not published),
`opencode.exe --version` → `v0.0.0-feat-truthprobe-…`,
an answer on the mock provider with `status: "ok", score: 0.417, first.score: 0.708, flagged: 1`.

### If you build the Windows binary from Linux/WSL

`bun install` on Linux does not download the platform optional dependencies of the other OS, while the
bundler requires them (`@opencode/pty-win32-x64`, `@opentui/core-win32-x64`, `@parcel/watcher-win32-x64`,
`@ff-labs/fff-bin-win32-x64` and the rest). The script solves this all at once:

```bash
OPENCODE_REPO=~/src/opencode python3 scripts/install-cross-deps.py win32
```

It reads the `optionalDependencies` of **all** packages in the bun store (including scoped directories),
downloads the missing win32 packages from npm and unpacks them next to their parent, the way
bun itself does. It is idempotent: a repeated run downloads nothing.

Pitfalls we have already stepped on:

- `pkg.parent` of a scoped package is the `@scope` directory, not `node_modules`; unpacking
  "next to the parent" without this correction creates `@scope/@scope/name`.
- Some dependencies (`@parcel/watcher-win32-x64`) are declared not in the root `package.json`
  but inside `.bun/@parcel+watcher@2.5.1/node_modules/@parcel/watcher`, so the traversal must be
  recursive rather than one level deep.

## Cross-compiling macOS

Not verified. By analogy: `install-cross-deps.py darwin` + `OPENCODE_TARGET=darwin-arm64`.
