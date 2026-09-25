# YANBF-CBC — YANBF Custom Banner CIA builder

A single-window tool for Windows and macOS that turns an icon, a banner (3D `.glb` model or
flat `.png`), optional audio and a few text fields into an installable 3DS
`.cia` forwarder for an NDS ROM (via YANBF's `forwarder.elf` / nds-bootstrap).

> **Unofficial.** YANBF-CBC is an independent fan-made front end. It is not
> affiliated with, endorsed by, or supported by the YANBF project, skyfloogle
> (pycgfx), Epicpkmn11 or Steveice10 (bannertool), PabloMK7 (cwavtool), 3DSGuy
> (Project_CTR), the tkinterdnd2/tkdnd authors, or Nintendo. Please don't ask
> those projects for help with this app. Report problems here instead. Nintendo
> 3DS and HOME Menu are trademarks of Nintendo. No ROMs or Nintendo software are
> included. Use your own legally dumped games.

One button runs the whole pipeline:

1. **Icon** – `bannertool makesmdh` → `icon.bin`
2. **Banner model** (`.glb` mode only) – pycgfx, run in-process → `banner.cgfx`
3. **Audio** – `cwavtool` → `audio.cwav`
4. **Banner** – `bannertool makebanner` (`-ci banner.cgfx` or `-i banner.png`) → `banner.bin`
5. **CIA** – `makerom` with `build-cia.rsf` + `forwarder.elf` → `{name}.cia`

Audio runs before the banner step because `makebanner` needs `audio.cwav`.

**Downloads:** see the repository's **Releases** page. There's a Windows zip and
two Mac zips, one for Apple Silicon (M1 and later) and one for Intel. On a Mac,
read [macOS](#macos) first.

## Folder layout

```
YANBF-CBC/
├── YANBF-CBC.exe          ← the program
├── processes/             ← MUST stay next to the exe
│   ├── Project_CTR/       ctrtool.exe, makerom.exe, bannertool.exe, cwavtool.exe
│   └── YANBF/
│       ├── generator/data/  build-cia.rsf, forwarder.elf, …
│       └── pycgfx/          main.py (patched), cgfx/
├── output/                ← created on first build
├── unique_ids.json        ← Unique IDs used so far (created on first build)
├── settings.json          ← saved options: where new IDs start, Light/Dark/System, 3DS FTP address (created on first save)
├── banner.blend           ← Blender template for 3D banners (also bundled in the exe; Template… button)
├── app/                   ← source code
├── patches/               ← this project's fixes to pycgfx (the repository doesn't contain pycgfx itself)
└── scripts/get_pycgfx.py  ← sets up processes/YANBF/pycgfx/ from the command line (the app offers it too)
```

`YANBF-CBC.exe` finds everything relative to **its own folder**, not the
current working directory. If you move it, move `processes/` with it.

## Required files and where they come from

| File | Source |
|---|---|
| `processes/Project_CTR/ctrtool.exe`, `makerom.exe` | [Project_CTR releases](https://github.com/3DSGuy/Project_CTR/releases) |
| `processes/Project_CTR/bannertool.exe` | [bannertool](https://github.com/Epicpkmn11/bannertool) (Epicpkmn11) |
| `processes/Project_CTR/cwavtool.exe` | [cwavtool](https://github.com/PabloMK7/cwavtool) (PabloMK7) |
| `processes/YANBF/generator/data/forwarder.elf` | [YANBF](https://github.com/YANBForwarder/YANBF) release asset (pre-compiled forwarder stub) |
| `processes/YANBF/generator/data/build-cia.rsf` | [YANBF](https://github.com/YANBForwarder/YANBF) generator (included) |
| `processes/YANBF/pycgfx/main.py` + `cgfx/` | [skyfloogle/pycgfx](https://github.com/skyfloogle/pycgfx) version `1f78850`, **patched**. Not in the repository: the program sets it up (see below) |

See [Credits](#credits) for authors and licenses.

### Setting up pycgfx

**pycgfx** has no license that allows sharing it, so the repository holds only
this project's two fixes, as `patches/pycgfx.patch`. The fixes are explained
in `patches/pycgfx-PATCH_NOTES.txt`. When pycgfx isn't there, the program opens
a **Set up pycgfx** window at startup, and again if you press Build. It says
which exact version to use (commit `1f78850`, 2 June 2025), and offers two
ways to set it up:

- **Automatic (recommended):** downloads that version's zip, about 3.2 MB,
  straight from skyfloogle's GitHub. It applies the fixes and checks every
  file byte for byte (SHA-256) against the tested version, then installs it
  in `processes/YANBF/pycgfx/`. It doesn't need git.
- **By hand:**
  1. The window links that version's zip.
  2. Copy `main.py`, `banner-camera.gltf` and the `cgfx` folder into the
     folder shown. Dropping the zip itself there, or the whole unzipped
     folder, works too.
  3. Press **Check again**. The program checks the version and adds the
     fixes itself.

Any other version of pycgfx is rejected, and the window names the files that
don't match. Once pycgfx checks out, the window doesn't appear again unless
the files are deleted or changed. `scripts/get_pycgfx.py` does the same
automatic setup from the command line, for example on a build machine:

```bat
python scripts\get_pycgfx.py
```

Don't replace the patched copy with stock pycgfx: without the fixes, the
`name`/`nameModel` logo doesn't billboard and some banners crash on hardware.

### Startup check

On startup the program checks for all of these. If pycgfx is missing, it
opens the setup window above. If anything else is missing, it shows one
error box listing the short paths (relative to the program's folder) and
puts the full paths in the log. Either way, **Build CIA** is disabled until
everything is in place. It checks again when you press Build.

## Fields

| Field | Required | Limits / notes |
|---|---|---|
| NDS ROM (.nds) | no | Only its header is read, to fill in the fields below. The ROM is never copied into the CIA |
| Icon image | yes | PNG only, exactly **48×48 px** (HOME Menu icon); any other size is rejected |
| Banner source | yes | **3D Model (.glb)**: `.glb` of at most **512 KB** (524,288 bytes; exactly 512 KB is allowed), the same limit pycgfx and the 3DS apply to the converted banner. **Template…** (3D Model mode) saves a ready-made Blender file, see [3D banner template](#3d-banner-template-bannerblend). **Flat Image (.png)**: PNG, at most **256×128 px** |
| Audio (.wav) | no | Uncompressed PCM WAV, at most **2.9375 s** long (the exact length of the reference clip "Freshly-Picked - Tingle's Rosy Rupeeland.wav": 141,000 frames at 48 kHz). Exactly 2.9375 s is allowed; anything longer is rejected. Empty → a 1-second silent 44.1 kHz stereo placeholder |
| ROM path on SD card | no | e.g. `/roms/nds/Some Game.nds`; written to `romfs/path.txt` as `sd:/roms/nds/Some Game.nds`. Empty → empty `path.txt` (warning: the forwarder won't find the ROM) |
| Title | yes | Used as both short and long title (`-s`/`-l`) and `APP_TITLE` |
| Publisher | no | `-p` for the SMDH |
| Product Code | yes | e.g. `CTR-H-TEST` |
| Unique ID (hex) | yes | 1–6 hex digits, `0x` optional (makerom's UniqueId is 24 bits). Title ID becomes `000400000` + ID + `00`, e.g. `FF3F0` → `000400000ff3f000` |
| Version (minor) | yes | 0–63 (major is 1, micro 0) |

### Filling fields from a .nds

Picking a `.nds` fills in these fields from the ROM header, the same way the
YANBF generator does:

| Field | Taken from |
|---|---|
| ROM path on SD card | `default_path.txt` (`/roms/nds/`) + the `.nds` file name |
| Title / Publisher | English banner title. 3 lines = title + subtitle, publisher; 2 lines = title, publisher; no banner = the 12-character internal name |
| Product Code | `CTR-H-` + the 4-character game code (header offset `0x0C`) |
| Unique ID | `unique_ids.json` (see below) |
| Version (minor) | ROM version byte (header offset `0x1E`) |

Filled fields are **locked**, and marked clearly in both Light and Dark: a
blue-grey tinted background, dimmed text and a **padlock** on their Edit
button. Press **Edit** next to a field to change
it, then **Save** to lock it again. Save is disabled while the value is
invalid, and Build is disabled while any field is unsaved. A value that isn't
in the header (such as a missing publisher, or a ROM version above 63) is
left empty and editable. Picking another `.nds` refills and relocks
everything. Clearing the `.nds` box unlocks all fields and keeps their
values.

### 3D banner template (`banner.blend`)

In 3D Model mode, **Template…** under the banner box saves a copy of
`banner.blend`, a Blender file already set up for a 3D banner. The Save As
dialog starts in Downloads. The file was saved with **Blender 5.2**, so open
it in 5.2 or newer. Its object tree is the one pycgfx and the 3DS HOME Menu
expect:

```
COMMON
├── world  → worldModel   the part that spins
└── name   → nameModel    the logo that always faces the viewer
```

Replace the models, keep the names, then use *File → Export → glTF 2.0* with
format **glTF Binary (.glb)**. The template is bundled inside the exe with
`--add-data`, so the button works without the loose file. In source mode it's
read from `banner.blend` in the project folder, and editing that file changes
what the button saves; rebuild the exe to update its copy.

### Unique IDs (`unique_ids.json`)

Every CIA installed on a 3DS needs its own Unique ID. Installing a CIA with
an ID that is already installed replaces that title. After each successful
build, the ID is saved in `unique_ids.json` next to the exe, keyed by the
game code (or by output name if no `.nds` was used). When you load a `.nds`:

- a game that was built before gets **the same ID** again, so the new CIA
  installs as an update;
- a new game gets **the next free ID** from the start set in Options…
  (default `FF400`, where YANBF's range begins) up to `FFFFF`.

If a build uses an ID that was saved for a different game, the log warns
you. Failed builds don't record anything.

**Choosing where new IDs start (Options…):** the **Options…** button next to
the Unique ID box sets where new games' IDs start, as an **offset from
`FF400`**. Use the up/down arrows or type a number; the start ID (hex) updates
automatically, and typing a start ID updates the offset too. A higher start
is useful if other forwarders on your 3DS already use IDs from `FF400`.

- Offset `0` = `FF400` (the default) up to offset `3071` = `FFFFF`, the
  highest ID. The dialog shows how many IDs are left and which ID the next
  new game would get.
- **Warning (amber):** the offset leaves **19 or fewer IDs** before `FFFFF`.
  You can still save.
- **Error (red):** the offset is **past the highest ID** (above 3071, or a
  start ID above `FFFFF`). Save is disabled until it's fixed.

The setting is saved in **`settings.json`** next to the exe and loaded every
time the program starts.
Games already in `unique_ids.json` keep their ID. If a `.nds` is loaded and
its ID was freshly suggested (not reused or hand-edited), saving a new start
updates it straight away.

### Drag and drop

Files can be dragged from Explorer instead of using Browse:

- Dropping on the **NDS ROM, Icon, Banner or Audio** row (or its preview box)
  fills that field.
- Known file types always go to their own field, wherever they're dropped:
  `.nds` → NDS ROM, `.wav` → Audio, `.glb` → Banner (switches to 3D Model).
- A `.png` goes to the row it's dropped on. Dropped anywhere else, it goes
  to Icon if it's exactly 48×48 px, otherwise to Banner (switches to Flat
  Image).
- Several files can be dropped at once. Each one is sorted as above, so
  dropping an icon, a model and a WAV together fills all three.
- Any other file type goes to the row it's dropped on, and validation
  explains the problem (e.g. "Icon must be a PNG (this file is JPEG)").
  Folders are ignored.

Each drop is logged ("Dropped icon.png → Icon") and the field flashes green.

### Previews

The panel on the right updates as soon as a file is picked:

- **Icon**: the PNG at 2× (pixel-exact) and at actual size, on a
  checkerboard so transparency is visible.
- **Banner, flat image**: the PNG at actual size (larger images are scaled to fit).
- **Banner, 3D model**: a software render of the `.glb` through the **3DS
  HOME Menu banner camera** (read from `pycgfx/banner-camera.gltf`), so the
  model's size and position roughly match the HOME Menu. Drag to rotate,
  use the mouse wheel to zoom (the label notes that zoom isn't the real
  size), and double-click to reset. It shows the static pose with base
  colour and textures and simple lighting. Animations, skinning,
  billboarding and the 3DS's exact lighting aren't simulated.
- **HOME Menu preview…** (3D banners): opens an animated window showing the
  model the way the HOME Menu presents it, through the banner camera, on a
  HOME Menu top screen at the native 400×240. The backdrop comes from
  `app/home_bg_screenshot.py`. Despite the name, it's a recreation made for
  this project, not a capture from a 3DS. Without that file, `app/home_bg.py`
  draws a plainer backdrop in the same colours and layout. The whole frame is rendered at the 3DS's
  400×240 and shown at 3× (1200×720) with a pixel grid that imitates the gaps
  between the screen's pixels. The grid is only a hint, and it's the same
  over the whole screen: the background, the banner model and the
  `name`/`nameModel` logo. Every pixel keeps its exact colour and the gaps are
  at 94%, so no detail is lost. That covers the status bar text and icons, the
  faint app-grid tiles, and the model's textures and logo:
  - the node named **`worldModel`** (or `world` if there's no `worldModel`)
    spins steadily about its own vertical axis. The default is 45°/s
    (8 s per turn); the slider changes it (negative = other direction), since
    the console's exact speed isn't known;
  - nodes named exactly **`name`** or **`nameModel`** are billboarded
    (YAxial), the mode the patched pycgfx gives those bones. They keep
    facing the screen even if they're children of the spinning model;
  - Pause, Reset spin and Play banner sound.
  It's rendered from the `.glb`, not from the converted `.cgfx`, and the
  lighting is approximate.
- **Audio**: waveform, duration, sample rate, bit depth and channels, with
  a Play/Stop button. With no audio selected it notes that 1 s of silence
  will be used.

## Output

`{name}` is the ROM file name without `.nds`, or the Title if the ROM path is
empty. It's cleaned for Windows (bad characters → `_`, reserved names such as
`CON` get a `_` prefix, `untitled` if nothing is left).

```
output/{name}/
├── {name}.cia
├── input files/
│   ├── icon.png
│   ├── banner_source.glb | banner_source.png
│   ├── audio.wav | silent_fallback.wav
│   └── romfs/path.txt        ← -DAPP_ROMFS points at this folder
└── produced files/
    ├── icon.bin
    ├── banner.cgfx           (glb mode only)
    ├── audio.cwav
    └── banner.bin
```

An existing `output/{name}/` is deleted and rebuilt. The log shows every
command line and all tool output. The first failing step stops the build
and is named in the log. pycgfx warnings are shown in amber, and
`CGFX is too big` is highlighted in orange (the build continues, but the
banner may not work on hardware).

## Sending to the 3DS (FTP)

**Send to 3DS…** in the button bar opens a window that uploads the files to
the 3DS over Wi-Fi, so you don't have to take the SD card out. On the 3DS,
start **ftpd** (an FTP server homebrew app). It shows the 3DS's IP address and
port on screen, usually port 5000. Enter them in the window and press
**Connect**. The PC and the 3DS must be on the same network.

The window lists both files together, each with a tick box. You can send both
in one go with **Send both to 3DS**, or untick one to send only the other.

| File | Comes from | Goes to |
|---|---|---|
| **CIA** | The last build in this session. If you haven't built this session, it looks in `output/` for a build matching the current fields. **Choose…** lets you pick any `.cia`. | The CIA folder you set (default `/cias/`) + the file name. Install it on the 3DS with FBI. |
| **NDS ROM** | The **NDS ROM** box in the main window. **Choose…** here fills that box too, so the CIA fields match the ROM. | Exactly the **ROM path on SD card** from the main window, which is where the forwarder looks. If that path has a different file name, the ROM is renamed to match. |

- **Progress:** each file has its own progress bar, speed and time left.
  **Cancel** stops the transfer.
- **Safe uploads:** a file is uploaded as `name.part` and renamed only once it
  is complete, so a cancelled or failed upload never leaves a half-written
  CIA or ROM on the SD card.
- **Replacing files:** if a file is already on the SD card, you're asked before
  it's replaced.
- **SD card browser:** the bottom half shows the SD card's folders. Double-click
  a folder to open it; **Up**, **Refresh** and **New folder…** are there too.
  **Send CIAs to this folder** makes the open folder the CIA destination.
- **Saved settings:** the IP address, port and CIA folder are saved in
  `settings.json`.

FTP to a 3DS is slow, usually well under 1 MB/s. A CIA takes a second or two,
but a large ROM can take several minutes. If connecting times out, check the
IP address, check that ftpd is still running, and check that Windows Firewall
or your antivirus allows the connection.

## macOS

The Mac app works like the Windows one. The differences:

- **Download:** unzip `YANBF-CBC-…-macOS-AppleSilicon.zip` (M-series Macs) or
  `…-macOS-Intel.zip` and move `YANBF-CBC.app` to Applications. The tools
  (`makerom`, `ctrtool`, `bannertool`, `cwavtool`) are inside the app, built for
  macOS.
- **First launch:** the app is only ad-hoc signed, not notarized by Apple, so
  macOS blocks it the first time. Open it once, then go to **System Settings →
  Privacy & Security** and press **Open Anyway**. On older macOS versions,
  right-click the app and choose **Open** → **Open** instead. Or, in Terminal:
  `xattr -dr com.apple.quarantine /Applications/YANBF-CBC.app`
- **pycgfx is not included, so download it by hand.** The Mac app never
  downloads it for you, so the **Set up pycgfx** window shows only the manual
  steps:
  1. Download exactly version `1f78850` (2 June 2025) from the link in the
     window. Don't use the green Code button on the main page, which gives
     the newest version.
  2. Put `main.py`, `banner-camera.gltf` and the `cgfx` folder (or the zip
     itself, or the unzipped folder) in
     `~/Library/Application Support/YANBF-CBC/pycgfx`. **Show in Finder** opens
     that folder.
  3. Press **Check again**. The app checks the version and adds its two fixes.
- **Where things are kept:** a Mac app can't write inside itself, so
  `settings.json` and `unique_ids.json` are in
  `~/Library/Application Support/YANBF-CBC/`. Built CIAs go to
  `~/Documents/YANBF-CBC/output/`.
- **Drag and drop** from Finder uses tkinterdnd2 (tkdnd), which is bundled in
  the app. **Intel Macs:** tkinterdnd2 has no tkdnd build for Intel Macs with
  Tk 9, so drag and drop is off there. Use the Browse buttons instead. **Audio preview** uses macOS's built-in `afplay`. **Appearance:**
  *System* follows macOS's light or dark mode. Title bars always follow
  macOS itself.

Everything else is the same, including the HOME Menu preview, Send to 3DS
and the Blender template.

## Credits

YANBF-CBC is an **unofficial** front end. The work of turning a banner, icon and
ROM path into a working forwarder is done by these projects. Thanks to their
authors. None of them made, endorse or support YANBF-CBC, so please report
problems with this app here, not to them. The same credits are in the app: press **Credits…** in the bottom bar (links open
in your browser).

### YANBF: Yet Another nds-Bootstrap Forwarder
<https://github.com/YANBForwarder/YANBF>

The forwarder itself: `processes/YANBF/generator/` (including `generator.py`,
`bannergif.py`, `data/build-cia.rsf` and `data/template.bcmdl`) and
`forwarder.elf`, the 3DS-mode program that launches the ROM through
nds-bootstrap. The `romfs/path.txt` format, the `CTR-H-` + game code product
code and the `FF400` Unique ID range all follow YANBF's generator.

- **lifehackerhansol**: `generator.py` and the CIA template
- **Pk11 (Epicpkmn11)**: `bannergif.py` and testing
- **Olmectron**: GUI wrapper
- YANBF itself credits **devkitPro** (toolchain) and **RocketRobz** (TWLNAND
  bootstrap code). It launches **nds-bootstrap** from DS-Homebrew.
- License: the bootstrap is **GPL-2.0** (originally © 2010 Dave "WinterMute"
  Murphy); the rest of YANBF is **MIT**.

### pycgfx
<https://github.com/skyfloogle/pycgfx>, by **skyfloogle**

Converts glTF (`.glb`) models into the CGFX format used by 3DS HOME Menu
banners. YANBF-CBC runs it in-process from `processes/YANBF/pycgfx/`. Its
`banner-camera.gltf` also provides the HOME Menu camera the banner previews
use. The copy included here is **patched** (see `PATCH_NOTES.txt`): every mesh
gets `mesh_node_name`, and bones named `name`/`nameModel` get YAxial billboard
mode. These are not upstream changes. GitHub shows no license for this
repository; see it for terms.

### bannertool
<https://github.com/Epicpkmn11/bannertool>, maintained by **Epicpkmn11**

Builds the HOME Menu icon (`makesmdh` → `icon.bin`) and the banner
(`makebanner` → `banner.bin`, from the CGFX or flat PNG plus the CWAV audio)
(`processes/Project_CTR/bannertool.exe`).

- Originally created by **Steveice10**.
- Epicpkmn11's repository is a fork of
  [Mtgxyz/bannertool](https://github.com/Mtgxyz/bannertool).
- License: **MIT**.

### cwavtool
<https://github.com/PabloMK7/cwavtool>, by **PabloMK7**

Converts the banner audio (`.wav`) to CWAV (`processes/Project_CTR/cwavtool.exe`).

- A modified version of **Steveice10**'s bannertool (see above).
- Uses **David Bryant**'s adpcm-xq (IMA-ADPCM) and **Jack Andersen**'s
  gc-dspadpcm-encode (DSP-ADPCM).
- License: **MIT** (per its README).

### Project_CTR
<https://github.com/3DSGuy/Project_CTR>, by **3DSGuy** (forked from
[bkifft/Project_CTR](https://github.com/bkifft/Project_CTR))

A collection of 3DS tools. YANBF-CBC uses:

- **makerom**: builds the final `.cia` (`processes/Project_CTR/makerom.exe`)
- **ctrtool**: reads and extracts 3DS files (`processes/Project_CTR/ctrtool.exe`). It's
  there for checking finished CIAs by hand, e.g. `ctrtool -i "output\Game\Game.cia"`
  shows the title ID and product code.

GitHub shows no license for this repository; see it for terms.

### tkinterdnd2 and tkdnd (Mac version only)
<https://github.com/Eliav2/tkinterdnd2> (originally by **pmgagne**) and
<https://github.com/petasis/tkdnd> by **Georgios Petasis**

Drag and drop from Finder in the macOS app. The Windows version uses its own
built-in drag and drop instead. License: **MIT** (tkinterdnd2) and
**BSD-style** (tkdnd).
