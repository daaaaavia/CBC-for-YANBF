YANBF-CBC builds YANBF forwarder CIAs with custom banners: a 3D `.glb` or flat PNG
banner, an icon, and banner audio. It can also send the finished files to your 3DS
over FTP.

## Downloads

| File | For |
|---|---|
| `…-Windows.zip` | Windows 10 / 11 (64-bit) |
| `…-macOS-AppleSilicon.zip` | Macs with an M-series chip (M1 and later) |
| `…-macOS-Intel.zip` | Intel Macs |

## Windows

1. Unzip the whole folder somewhere you can write to, such as Documents. Keep
   `YANBF-CBC.exe` next to the `processes` folder.
2. Run `YANBF-CBC.exe`. If SmartScreen warns about it, choose **More info → Run anyway**.
3. The first time, a **Set up pycgfx** window opens. Press **Download and set up
   automatically**, or follow the steps to do it by hand.

## macOS

1. Unzip it and move `YANBF-CBC.app` to Applications.
2. **First launch:** the app isn't notarized by Apple, so macOS blocks it the first
   time. Open it once, then go to **System Settings → Privacy & Security** and press
   **Open Anyway**. On older macOS versions, right-click the app and choose **Open**
   instead. Or run this in Terminal:
   `xattr -dr com.apple.quarantine /Applications/YANBF-CBC.app`
3. **pycgfx isn't included in the Mac app, so download it yourself.** The
   **Set up pycgfx** window links the exact version needed, `1f78850`. Put its files
   (or the zip) in `~/Library/Application Support/YANBF-CBC/pycgfx`. The
   **Show in Finder** button opens that folder. Then press **Check again**.

On a Mac, settings and the Unique ID list are kept in
`~/Library/Application Support/YANBF-CBC`. Built CIAs go to
`~/Documents/YANBF-CBC/output`.

## Why pycgfx isn't included

pycgfx by skyfloogle has no license that allows sharing it, so it always comes from
its own GitHub. Build CIA stays disabled until it's set up.
