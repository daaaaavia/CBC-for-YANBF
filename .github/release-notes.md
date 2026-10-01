Make 3DS forwarders for your DS games, with your own icon, banner (3D or flat) and
sound. You can also send the finished files to your 3DS over Wi-Fi.

> **Unofficial.** Not affiliated with or supported by YANBF, pycgfx, bannertool,
> cwavtool, Project_CTR, tkinterdnd2/tkdnd or Nintendo. Please report problems
> here, not to them. No ROMs or Nintendo software are included.

## What's new in v1.0.4

- **Edit existing CIAs.** Change the icon, titles, banner or sound of a CIA you
  already have, with old and new side by side. The edited copy goes up one
  version, so it installs over the original.
- **Transparent banners no longer crash the HOME Menu.** pycgfx left the bone
  lookup table pointing at the wrong bones when a model had a transparent
  (BLEND) material. The app now fixes that and marks those materials as
  translucent.
- **Troubleshooting** in the README, for games that get stuck on a white screen.

## Which file?

- **Windows:** `…-Windows.zip`
- **Mac with an M-series chip (M1 or later):** `…-macOS-AppleSilicon.zip`
- **Intel Mac:** `…-macOS-Intel.zip`

## Windows

1. Unzip it somewhere like Documents, and keep `CBC-for-YANBF.exe` next to the
   `processes` folder.
2. Run `CBC-for-YANBF.exe`. If SmartScreen warns you, choose **More info → Run anyway**.
3. The first time, press **Download and set up automatically** to get pycgfx
   and ctrtool.

## macOS

1. Unzip it and move `CBC-for-YANBF.app` to Applications.
2. The app isn't notarized by Apple, so macOS blocks it the first time. Open it
   once, then go to **System Settings → Privacy & Security** and press **Open
   Anyway**.
3. Download pycgfx and ctrtool by hand. The setup window has the links and
   shows where the files go.

Your CIAs are saved in `~/Documents/CBC-for-YANBF/output`. Drag and drop doesn't
work on Intel Macs, so use Browse there.

## Why pycgfx and ctrtool aren't included

Neither has a license that allows sharing it, so they have to come from their
authors' GitHub pages. The app checks that you've got the right versions.
