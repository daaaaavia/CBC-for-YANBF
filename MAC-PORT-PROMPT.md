# Prompt: port YANBF-CBC to macOS

> This is a task prompt for a future Claude Code session. It hasn't been acted
> on yet. To start, open a session in this folder and ask it to follow
> `MAC-PORT-PROMPT.md`.

---

## Goal

Make YANBF-CBC run on macOS as a double-clickable `YANBF-CBC.app`, while the
Windows version keeps working **exactly** as it does now.

Do the work in three phases. **Stop after each phase and report** before
starting the next:

1. Make the Python code cross-platform. This can be done and tested on Windows.
2. Add a GitHub Actions workflow that builds the Mac app and its native tools.
3. Update the docs.

## Context

- **The app:** a Python 3.14 + tkinter GUI in `app/`. It runs the pipeline
  icon → pycgfx (`.glb` → CGFX, run in-process) → cwavtool → `bannertool
  makebanner` → makerom and produces a 3DS `.cia` forwarder for YANBF. It also
  has previews, a HOME Menu preview, drag and drop, Light/Dark/System themes,
  a Unique ID registry and a *Send to 3DS* FTP window.
- **Windows build:** a PyInstaller one-file exe (`YANBF-CBC.exe`) next to
  `processes/`. See `README.md` for the full technical reference and
  `USER_GUIDE.md` for how it's used.
- **Paths:** everything resolves from `paths.BASE_DIR`: the exe's folder when
  frozen, or the parent of `app/` in source mode.
- **Native tools:** `processes/Project_CTR/{makerom,ctrtool,bannertool,cwavtool}.exe`
  are Windows builds. macOS needs its own builds of each.
- **Repository:** the code is in a private GitHub repo. Two files have no
  license that allows sharing, and they're handled differently:
  - **pycgfx:** `app/pycgfx_setup.py` downloads upstream at a pinned commit
    (a zip, no git needed), applies the built-in fixes (the same as
    `patches/pycgfx.patch`) and checks every file by SHA-256. The app shows
    `app/pycgfx_window.py` at startup when pycgfx isn't the tested version.
    `scripts/get_pycgfx.py` does the same from the command line.
    **The user's decision for macOS: pycgfx is NOT included in the Mac app, and
    Mac users download it manually.** So on macOS:
    - **Don't bundle pycgfx** into the `.app` or the release zip.
    - **Manual option only:** the setup window shows just the by-hand
      instructions (the exact-version zip link, where to put the files, and
      Check again). Hide the "Download and set up automatically" option, and
      don't download anything on the user's behalf.
    - **User-writable location:** files can't be added inside a signed `.app`,
      so point `paths.PYCGFX_DIR` at
      `~/Library/Application Support/YANBF-CBC/pycgfx` on macOS. Show that
      path in the window with a button that opens it in Finder.
    - **Keep the rest:** version checking, the automatic fixes on Check again,
      "don't show again once it checks out", and accepting the zip or the
      unzipped folder placed there.
    - **Windows is unchanged:** it keeps both options.
  - **The HOME Menu backdrop** (`app/home_bg_screenshot.py`) is committed and
    used on every platform. Despite its name it's a recreation made for this
    project, not a capture from a 3DS. Keep the plain-backdrop fallback in
    `app/home_bg.py`.

## Hard rules

- **Keep Windows identical.** Every change must be behind a platform check or be
  genuinely cross-platform. After phase 1, rebuild the Windows exe and confirm
  it behaves the same.
- **Don't modify** `processes/YANBF/pycgfx/main.py` or `cgfx/` (the patched
  pycgfx), `patches/pycgfx.patch`, or any native tool binary.
- **Never touch the user's real data:**
  - `settings.json` and `unique_ids.json` next to the exe;
  - `output/`.
  Tests must point `paths.SETTINGS`, `paths.ID_REGISTRY` and
  `paths.OUTPUT_DIR` at scratch files.
- **No new runtime dependencies** unless listed below. Keep `requirements.txt`
  accurate.
- **Match the existing code style:** comment density, naming, plain-English
  error messages.

## Phase 1 - cross-platform code

These are all the Windows-specific spots found in `app/`. Add a small
`platform_util.py` (or similar) rather than scattering `sys.platform` checks.

| Where | Windows today | macOS replacement |
|---|---|---|
| `paths.py` | Tool names end in `.exe` | No extension on macOS/Linux. **Frozen .app:** `sys.executable` is inside `YANBF-CBC.app/Contents/MacOS/`. Look for `processes/` in `Contents/Resources/processes` first, then next to the `.app`. **User data:** write `settings.json`, `unique_ids.json` and `output/` to a writable location: `~/Library/Application Support/YANBF-CBC/` for the two JSON files, and `~/Documents/YANBF-CBC/output` for output. Never write inside the bundle. Keep Windows paths unchanged. |
| `pipeline.py` | `creationflags=CREATE_NO_WINDOW` (falls back to `0x08000000`) | **Must be 0 or omitted on non-Windows.** A non-zero `creationflags` raises `ValueError` on POSIX. Also make sure the tools are executable (`chmod +x` if needed) and give a clear error if macOS quarantine blocks them. |
| `yanbf_cbc.py`, `home_preview.py` | `winsound.PlaySound(..., SND_ASYNC)` and `PlaySound(None, 0)` to stop | Start `afplay <file>` with `subprocess.Popen` and `terminate()` it to stop. Keep the existing "play ended" behaviour: the Play button returns to ▶ when the clip finishes, which can be done by polling the process. Import `winsound` only on Windows. |
| `yanbf_cbc.py`, `pycgfx_window.py` | `os.startfile(path)` for the output folder and the pycgfx folder | `subprocess.run(["open", path])` on macOS, `xdg-open` on Linux. |
| `dragdrop.py` | Win32 `WM_DROPFILES` via ctypes | Use **`tkinterdnd2`** on macOS (the one allowed new dependency; it bundles tkdnd). Keep the ctypes version on Windows, since it is tested and working. The drop callback must keep the same contract (`callback(paths, x_root, y_root)`, queued to the Tk loop) so `route_drop` / `handle_drop` / `zone_at` are unchanged. If tkinterdnd2 can't load, disable drag and drop quietly (Browse still works) and log a tip. |
| `theme.py` `system_is_dark()` | Windows registry `AppsUseLightTheme` | `defaults read -g AppleInterfaceStyle` (prints `Dark` in dark mode; exits non-zero in light mode). |
| `theme.py` `set_title_bar()` | DWM dark title bar | No-op on macOS: title bars follow the system appearance. |
| `theme.py` light mode | Restores the native ttk theme (`vista` on Windows) | On macOS the native theme is `aqua`, and restoring it the same way should work. Check that the `clam`-based dark theme still looks right on a Mac and doesn't clash with a light system appearance. |
| `theme.py` fonts | `Segoe UI`, `Consolas` | Use `SF Pro` / `Helvetica Neue` and `Menlo` on macOS (Tk falls back silently, but sizes differ). Point sizes may need +2 on macOS for the same visual size. |
| `yanbf_cbc.py` `root.minsize(1120, 720)` and fixed widths | Tuned for Windows fonts | Check the layout on macOS; nothing must be clipped (see the "button bar at minimum width" test). |
| `home_preview.py` | Fixed `SCALE = 3` window (1200×720) | Fine on Mac, but check it fits a 13" MacBook screen (1440×900 logical). |
| `<MouseWheel>` in the banner preview | Only uses the sign of `event.delta` | Already works on macOS. Leave it alone. |

**Also check:**
- **Any other Windows assumptions:** backslashes in paths shown to the user,
  `\r\n`, drive letters in `output_name` sanitising (keep Windows' reserved-name
  rules; they're harmless on Mac).
- **FTP window (`ftp_window.py`, `ftp3ds.py`):** stdlib only, so it should
  already work. Confirm it does.
- **pycgfx loading:** pycgfx is loaded from disk with `importlib`. Confirm that
  works from inside a frozen `.app`.

**Tests (phase 1):**
- **Existing suites:** `tests/run_all.py` runs the 15 suites in
  `tests/suite_*.py` (see the README's *Tests* section). They generate their
  own inputs and never touch the user's data. A few checks are gated on
  `WINDOWS` in `tests/_common.py`, such as the native ttk theme and the drag
  and drop suite. Give those macOS equivalents rather than deleting them, and
  add the new tests as `tests/suite_*.py` too.
- **New tests:** cover the platform helpers with `sys.platform` monkeypatched
  to `darwin`:
  - tool names;
  - frozen `.app` path resolution;
  - user-data locations;
  - `creationflags` omitted;
  - the audio command built;
  - the open command built;
  - dark mode parsing of `defaults` output (both `Dark` and the non-zero
    light-mode case).
- **Windows:** run all of them on Windows; everything must pass.

**Phase 1 is done when:**
- the source runs on Windows unchanged;
- all tests pass;
- the Windows exe has been rebuilt and verified (starts, builds a CIA, FTP
  window opens);
- the code is ready to run on a Mac.

## Phase 2 - GitHub Actions build

Create `.github/workflows/build-macos.yml`, triggered manually
(`workflow_dispatch`) and on tags. On `macos-latest`:

1. **Tools:** build or fetch the four native tools **for both arm64 and
   x86_64**, then combine each pair with `lipo` into universal binaries:
   - **makerom, ctrtool:** download the macOS builds from the
     [Project_CTR releases](https://github.com/3DSGuy/Project_CTR/releases),
     or build from source if a universal build isn't provided.
   - **bannertool:** build from source,
     [Epicpkmn11/bannertool](https://github.com/Epicpkmn11/bannertool).
   - **cwavtool:** build from source,
     [PabloMK7/cwavtool](https://github.com/PabloMK7/cwavtool).
   - **Record the versions:** record the exact commit or release used for each
     tool in the workflow, so builds are reproducible.
2. **Python:** set up Python 3.14 (python.org universal2 build, with Tk 8.6+
   or 9) and install `requirements.txt`, `tkinterdnd2` and PyInstaller. For
   the tests only, run `python scripts/get_pycgfx.py`. The workflow may
   download pycgfx to test with it, but it must never end up in the app.
3. **App bundle:** run PyInstaller with `--windowed --target-arch universal2`
   to produce `YANBF-CBC.app`.
   - **Copy in the data:** copy `processes/` into
     `Contents/Resources/processes`, with the Mac tools in place of the
     `.exe`s and the same `YANBF/` data. **Leave out `processes/YANBF/pycgfx/`**:
     Mac users download pycgfx themselves. Add a workflow check that fails the
     build if any pycgfx file is inside the `.app` or the zip.
   - **Hidden imports:** use the same hidden imports as the Windows build
     (`gltflib`, `PIL.Image`, `argparse`), plus whatever tkinterdnd2 needs.
4. **Ad-hoc signing:** run `codesign --force --deep -s - YANBF-CBC.app` so
   Apple Silicon will run it.
5. **Smoke test:** on the runner:
   - run the frozen app's tool paths with `--help`;
   - run a headless build of a small test CIA through `pipeline.py` and check
     `ctrtool` can read the result. Use a flat PNG banner, or a
     test-only pycgfx outside the `.app`.
   - check that the frozen app, started with no pycgfx in its Application
     Support folder, reports pycgfx as missing and not the other tools.
6. **Publish:** zip it (`ditto -c -k --keepParent`) and upload
   `YANBF-CBC-macOS.zip` as the build artifact. Attach it to the release when
   triggered by a tag.

**Out of scope:** notarization and Developer ID signing (they need a paid
Apple account). Document the first-launch Gatekeeper step instead.

**Phase 2 is done when:** the workflow file exists, has been checked for
syntax (for example with `actionlint` if it's available), and every tool
source and version is written down. Say plainly that it can only really be
verified by running it on GitHub.

## Phase 3 - docs

- **README:** add a *macOS* section covering:
  - download and unzip;
  - the first launch (right-click → **Open** → **Open**, or
    `xattr -dr com.apple.quarantine YANBF-CBC.app`);
  - where settings, IDs and output are stored on a Mac;
  - **downloading pycgfx by hand:**
    - it isn't included in the Mac app;
    - use exactly version `1f78850` from the link in the setup window;
    - put the files in `~/Library/Application Support/YANBF-CBC/pycgfx`;
    - press **Check again**;
  - how to build locally on a Mac and via GitHub Actions;
  - which features differ, if any.
- **USER_GUIDE.md:** add short Mac notes where behaviour differs:
  - Finder instead of Explorer;
  - the Gatekeeper step in *Before you start*;
  - the output location.

  Don't retake the screenshots. Say in the guide that they show Windows.
  Regenerate `USER_GUIDE.html` with `app/make_guide_html.py`.
- **Credits:** check the Credits section and the in-app Credits window still
  apply (tkinterdnd2 / tkdnd should be credited: tkinterdnd2 is MIT and tkdnd
  is BSD-style; check both).

## Report at the end

- **Changes:** what changed, file by file.
- **Verified vs unverified:** what was tested on Windows, and what can only
  be checked on a real Mac (list it plainly).
- **Manual Mac checklist** for the user: launch, theme follows the system,
  drag and drop from Finder, audio play/stop, HOME Menu preview, build a CIA,
  install it on a 3DS, and send files to the 3DS over FTP.
