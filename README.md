# CBC for YANBF

**Custom Banner CIA builder for YANBF**

CBC for YANBF makes 3DS forwarders for your DS games, with your own icon, banner and
sound. Pick a `.nds`, an icon, a 3D (`.glb`) or flat (`.png`) banner and an
optional `.wav`, press **Build CIA**, and you get a `.cia` that launches the game
through YANBF and nds-bootstrap. It runs on Windows and macOS.

> **Unofficial.** CBC for YANBF is an independent fan-made tool. It isn't affiliated
> with, endorsed by or supported by YANBF, skyfloogle (pycgfx), Epicpkmn11 or
> Steveice10 (bannertool), PabloMK7 (cwavtool), 3DSGuy (Project_CTR), the
> tkinterdnd2/tkdnd authors, or Nintendo. Please report problems here, not to
> them. Nintendo 3DS and HOME Menu are trademarks of Nintendo. No ROMs or
> Nintendo software are included, so use your own legally dumped games.

**Download** it from the **Releases** page. There's a Windows zip and two Mac
zips: Apple Silicon (M1 and later) and Intel. Mac users should read
[macOS](#macos) first.

## What it does

One button runs every step:

1. **Icon:** `bannertool makesmdh` → `icon.bin`
2. **3D banner:** pycgfx turns the `.glb` into `banner.cgfx` (3D mode only)
3. **Audio:** `cwavtool` → `audio.cwav`
4. **Banner:** `bannertool makebanner` → `banner.bin`
5. **CIA:** `makerom` with YANBF's `forwarder.elf` → `{name}.cia`

## Getting started

Unzip the Windows download somewhere you can write to, such as Documents, and
run `CBC-for-YANBF.exe`. Keep the `processes` folder next to it, because that's
where the tools live:

```
CBC-for-YANBF/
├── CBC-for-YANBF.exe
├── processes/        the tools (keep this next to the exe)
├── output/           your CIAs (made on the first build)
├── unique_ids.json   IDs used so far
└── settings.json     your options
```

### pycgfx and ctrtool

Two files come from other projects and aren't included: **pycgfx** by
skyfloogle, which turns 3D banners into the 3DS format, and **ctrtool** from
3DSGuy's Project_CTR, which reads finished CIAs. pycgfx doesn't have any license
mention and ctrtool has no license published, so neither can be shared. The
first time you start the app, a **Set up downloads** window helps you get both.
Use exactly pycgfx `1f78850` (2 June 2025) and ctrtool `1.3.0`. The app checks
every file and won't accept any other version.

- **Automatic (Windows):** press **Download and set up automatically**. It
  fetches whichever are missing from their authors' GitHub pages (about 4 MB)
  and adds this project's two small fixes to pycgfx.
- **By hand:** each file has its own link and folder in the window. For
  pycgfx, don't use the green Code button, because that gives the newest
  version. Put `main.py`, `banner-camera.gltf` and the `cgfx` folder (or just
  the zip) in its folder. For ctrtool, put the zip, or the `ctrtool` file
  inside it, in its folder. Then press **Check again**.

The window can't be closed until both files are set up, and **Build CIA**
stays disabled until then. After that, the window doesn't come back.

### Changes to pycgfx

pycgfx is the only outside tool this app changes. Everything else (makerom,
ctrtool, bannertool, cwavtool and YANBF's files) is used exactly as its authors
released it. pycgfx is downloaded unmodified from skyfloogle's GitHub, checked
file by file, and then two small fixes are added to its `main.py`. The fixes
are about 4 lines in total, and the `cgfx/` library files aren't touched:

1. **Every mesh gets its node name** (`mesh_node_name`). Stock pycgfx leaves it
   blank, and some banners crashed on the 3DS without it.
2. **The logo faces you.** Bones named exactly `name` or `nameModel` get the
   YAxial billboard mode, so the logo keeps facing the screen while the rest of
   the banner spins. Stock pycgfx never sets this mode.

Both were needed for a working 3D banner with a logo on real hardware. The
fixes are in `patches/pycgfx.patch` and explained in
`patches/pycgfx-PATCH_NOTES.txt`. They're this project's changes, not part of
pycgfx, so please don't report problems with them to skyfloogle.

## Fields

| Field | Required | Notes |
|---|---|---|
| NDS ROM | no | Only the header is read, to fill in the fields. The ROM itself isn't put in the CIA. |
| Icon | yes | A 48×48 PNG. |
| Banner | yes | A **3D model** (`.glb`, up to 512 KB) or a **flat image** (PNG, up to 256×128). |
| Audio | no | An uncompressed WAV, up to 2.9375 s. If left empty, 1 s of silence is used. |
| ROM path on SD card | no | Where the game is on the SD card, e.g. `/roms/nds/Game.nds`. Without it, the forwarder can't find the game. |
| Title | yes | The name shown on the HOME Menu. |
| Publisher | no | |
| Product Code | yes | e.g. `CTR-H-TEST` |
| Unique ID | yes | 1–6 hex digits. Every forwarder needs its own. |
| Version | yes | 0–63 |

### Filling fields from a .nds

Picking a `.nds` fills in the title, publisher, product code, version, SD path
and Unique ID from the ROM, the same way YANBF's generator does. Those fields
are then **locked**. Press **Edit** to change one and **Save** to lock it again.
Clearing the ROM box unlocks everything.

### Unique IDs

Installing a CIA with an ID that's already in use replaces that title, so each
game needs its own ID. The app remembers the IDs it has used in
`unique_ids.json`:

- rebuilding a game gives it **the same ID**, so it installs as an update;
- a new game gets **the next free ID**, starting at `FF400` (YANBF's range).

If other forwarders on your 3DS already use IDs from `FF400`, **Options…** lets
you start higher. It warns you when you're close to running out (the last ID
is `FFFFF`).

### 3D banner template

In 3D mode, **Template…** saves `banner.blend`, a Blender file (5.2 or newer)
that's already set up the way the HOME Menu expects:

```
COMMON
├── world  → worldModel   the part that spins
└── name   → nameModel    the logo that always faces you
```

Swap in your own models, keep the names, and export with *File → Export →
glTF 2.0*, using the **glTF Binary (.glb)** format.

**Important note:** Before exporting make sure all items in the `COMMON` 
hierarchy are selected and all transformations are applied.

### Drag and drop

You can drag files onto the window instead of using Browse. Drop a file on a
row to fill it, or drop several files anywhere and each one goes where it
belongs: `.nds`, `.wav` and `.glb` by type, and a PNG to Icon if it's 48×48,
otherwise to Banner.

### Previews

The panel on the right shows each file as soon as you pick it:

- **Icon:** at 2× and actual size.
- **Banner:** the PNG, or the 3D model through the HOME Menu's banner camera.
  Drag to rotate, scroll to zoom, double-click to reset.
- **HOME Menu preview…:** an animated view of a 3D banner on a recreated
  HOME Menu screen, at the 3DS's resolution. `worldModel` spins (the speed is
  adjustable) and the `name` logo keeps facing you. It's a close
  approximation, not an exact match for the console.
- **Audio:** the waveform and details, with Play/Stop.

## Output

Each build goes in its own folder, named after the ROM file (or the title if
there's no ROM path):

```
output/{name}/
├── {name}.cia
├── input files/      copies of what you picked
└── produced files/   icon.bin, banner.cgfx, audio.cwav, banner.bin
```

Building the same game again replaces its folder. The log shows every command
and its output. If a step fails, the log says which one. A 3D banner that's too
big for the 3DS is flagged in orange.

## Sending to the 3DS (FTP)

**Send to 3DS…** uploads the CIA and the ROM over Wi-Fi, so you don't need to
take the SD card out.

1. On the 3DS, start **ftpd**. It shows an IP address and port (usually 5000).
2. Enter them and press **Connect**. The computer and the 3DS need to be on the
   same network.
3. Tick the files you want and press **Send**.

The CIA goes to your CIA folder (`/cias/` by default), ready to install with
FBI. The ROM goes to the exact **ROM path on SD card** from the main window, so
the forwarder can find it. Each file shows its own progress and time left.
Files are uploaded under a temporary name and only renamed once complete, so a
cancelled upload never leaves a broken file. You're asked before anything is
replaced. You can also browse the SD card and make folders.

FTP to a 3DS is slow, usually under 1 MB/s. A CIA takes seconds, but a big ROM
can take minutes. If it won't connect, check the IP address, check that ftpd
is still running, and check that your firewall allows the connection.

## macOS

The Mac app works like the Windows one, with a few differences:

- **Installing:** unzip the Apple Silicon or Intel zip and move `CBC-for-YANBF.app`
  to Applications.
- **First launch:** the app isn't notarized by Apple, so macOS blocks it the
  first time. Open it once, then go to **System Settings → Privacy &
  Security** and press **Open Anyway**. On older macOS versions, right-click
  the app and choose **Open**. You can also run
  `xattr -dr com.apple.quarantine /Applications/CBC-for-YANBF.app` in Terminal.
- **pycgfx and ctrtool have to be downloaded by hand.** Follow the steps
  in the setup window. The files go in
  `~/Library/Application Support/CBC-for-YANBF/pycgfx` and `…/ctrtool`, and **Show
  in Finder** opens the right folder. For ctrtool, get `macos_arm64` for
  Apple Silicon or `macos_x86_64` for Intel. The app makes it runnable for you
  once it checks out.
- **Where things are kept:** settings and IDs are in
  `~/Library/Application Support/CBC-for-YANBF/`, and CIAs are in
  `~/Documents/CBC-for-YANBF/output/`.
- **Drag and drop** doesn't work on Intel Macs, so use Browse there. It works
  on Apple Silicon.

## Credits

CBC for YANBF is just a front end. The real work is done by these projects, and
thanks go to their authors. None of them made or support this app. The same
credits are in the app under **Credits…**.

- **[YANBF](https://github.com/YANBForwarder/YANBF)** (Yet Another
  nds-Bootstrap Forwarder): the forwarder itself (`forwarder.elf`,
  `build-cia.rsf` and the generator this app follows). By lifehackerhansol
  (generator, CIA template), Pk11 / Epicpkmn11 (`bannergif.py`, testing) and
  Olmectron (GUI wrapper). YANBF credits devkitPro and RocketRobz, and it
  launches nds-bootstrap by DS-Homebrew. Its bootstrap is GPL-2.0
  (© 2010 Dave "WinterMute" Murphy) and the rest is MIT.
- **[pycgfx](https://github.com/skyfloogle/pycgfx)** by skyfloogle: converts
  `.glb` models to the 3DS banner format, and its banner camera drives the
  previews. This app adds two fixes of its own. The fixes aren't part of
  pycgfx. No license is shown on GitHub.
- **[bannertool](https://github.com/Epicpkmn11/bannertool)**, maintained by
  Epicpkmn11 (a fork of Mtgxyz/bannertool, originally by Steveice10): builds
  the icon and banner. MIT.
- **[cwavtool](https://github.com/PabloMK7/cwavtool)** by PabloMK7 (based on
  Steveice10's bannertool, using David Bryant's adpcm-xq and Jack Andersen's
  gc-dspadpcm-encode): converts the audio. MIT.
- **[Project_CTR](https://github.com/3DSGuy/Project_CTR)** by 3DSGuy (forked
  from bkifft/Project_CTR): makerom builds the CIA and is MIT (the license is
  in its folder). ctrtool reads finished CIAs. It has no license shown, so the
  app downloads it from Project_CTR's releases instead of including it.
- **[tkinterdnd2](https://github.com/Eliav2/tkinterdnd2)** (originally by
  pmgagne) and **[tkdnd](https://github.com/petasis/tkdnd)** by Georgios
  Petasis: drag and drop in the Mac app. MIT and BSD-style.

## License

CBC for YANBF is MIT licensed (see `LICENSE`). The tools and libraries it includes
keep their own licenses, collected in `THIRD_PARTY_LICENSES.txt`.
