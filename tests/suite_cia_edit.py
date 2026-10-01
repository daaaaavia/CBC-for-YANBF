"""The Edit CIA feature (app/cia_edit.py + cia_edit_page.py). Builds real
CIAs with the real tools, changes the icon, titles, banner and sound (each alone and
together), and checks every result with ctrtool: same Title ID, all hashes GOOD, the
new parts in place and the untouched parts byte-identical. Also: encrypted CIAs and
non-CIAs are refused, the original is never changed, and the edit mode of the main
window works."""
import os
import shutil
import struct
import subprocess
import time

from _common import S, check, finish, isolate, skip
isolate("cia_edit")
import paths
import pipeline as pl

if paths.find_missing():
    skip("the real tools aren't all set up")
import cia_edit as ce  # noqa: E402
import fixtures  # noqa: E402
from PIL import Image  # noqa: E402

W = os.path.join(S, "cia_edit")
shutil.rmtree(W, ignore_errors=True)
os.makedirs(W)


def build(mode, banner, audio, uid, title):
    job = pl.BuildJob(icon_path="icon48.png", banner_mode=mode, banner_path=banner, audio_path=audio,
                      rom_path=f"/roms/nds/{title}.nds", title=title, publisher="Tester",
                      product_code="CTR-H-EDIT", unique_id=uid, minor=0)
    p = pl.Pipeline(job, lambda k, s: None, output_root=os.path.join(W, "built"), registry_path=paths.ID_REGISTRY)
    assert p.run(), f"test build failed: {mode}"
    return p.cia_path


def ctrtool_ok(cia):
    """(all hashes GOOD, the ExeFS files) as ctrtool sees them."""
    d = os.path.join(W, "ct_" + os.path.basename(cia).replace(" ", "_"))
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copyfile(cia, os.path.join(d, "x.cia"))
    r = subprocess.run([paths.CTRTOOL, "-y", "--exefsdir=exefs", "x.cia"], cwd=d, capture_output=True, text=True,
                       errors="replace")
    lines = [ln for ln in r.stdout.splitlines() if "hash" in ln.lower() and ("GOOD" in ln or "FAIL" in ln)]
    good = bool(lines) and not any("FAIL" in ln for ln in lines)
    files = {}
    for n in ("icon.bin", "banner.bin"):
        p = os.path.join(d, "exefs", n)
        files[n] = open(p, "rb").read() if os.path.isfile(p) else None
    tid = next((ln.split()[-1] for ln in r.stdout.splitlines() if ln.startswith("Title id:")), None)
    return good, files, tid


def pattern_icon(path):
    img = Image.new("RGB", (48, 48))
    px = img.load()
    for y in range(48):
        for x in range(48):
            px[x, y] = (x * 5, y * 5, (x ^ y) * 4)
    img.save(path)
    return img


print("reading")
png_cia = build(pl.MODE_PNG, "banner256.png", "", "FF3E1", "Edit Flat")
glb_cia = build(pl.MODE_GLB, "test.glb", os.path.join("wav", "clip_288.wav"), "FF3E2", "Edit Model")
info = ce.read_cia(png_cia)
check(info.title_id == "000400000ff3e100" and info.product_code == "CTR-H-EDIT", f"ids: {info.title_id} {info.product_code}")
check(info.titles == ("Edit Flat", "Edit Flat", "Tester"), f"titles: {info.titles}")
check(info.has_sound and abs(info.sound_seconds - 1.0) < 0.01, f"sound: {info.sound_seconds}")
g = ce.read_cia(glb_cia)
check(abs(g.sound_seconds - 2.88) < 0.01, f"glb build's sound: {g.sound_seconds}")
good, files, tid = ctrtool_ok(png_cia)
check(good and files["icon.bin"] == info.icon and files["banner.bin"] == info.banner, "reads what ctrtool reads")

print("icon picture only")
icon_png = os.path.join(W, "pattern.png")
src = pattern_icon(icon_png)
orig_bytes = open(png_cia, "rb").read()
out = ce.run(ce.EditJob(cia_path=png_cia, icon_png=icon_png), lambda k, s: None)
check(out == os.path.join(paths.OUTPUT_DIR, "Edit Flat (edited)", "Edit Flat (edited).cia") and os.path.isfile(out),
      f"saved as ... (edited).cia in output/: {out}")
check(open(png_cia, "rb").read() == orig_bytes, "the original CIA is unchanged")
good, files, tid = ctrtool_ok(out)
e = ce.read_cia(out)
check(good and tid == "000400000ff3e100", f"ctrtool: all hashes GOOD, same Title ID ({tid})")
diff = max(abs(a - b) for pa, pb in zip(list(ce.smdh_icon(e.icon).get_flattened_data()), list(src.get_flattened_data())) for a, b in zip(pa, pb))
check(diff <= 8, f"new icon in place (largest difference {diff}, RGB565 rounding)")
check(e.titles == info.titles and e.banner == info.banner, "titles and banner untouched")
check(info.version == (1 << 10) and ce.version_text(info.version) == "v1.0.0 (1024)", f"built as v1.0.0: {info.version}")
check(e.version == info.version + 1, f"edited copy is one version up: {ce.version_text(e.version)}")
_, secs = ce._parse_cia(open(out, "rb").read())
tik = struct.unpack_from(">H", secs["ticket"], ce._ticket_version_at(secs["ticket"]))[0]
check(tik == e.version, f"ticket version matches the TMD ({tik})")
again = ce.run(ce.EditJob(cia_path=out, titles=("Again", "Again", "Me")), lambda k, s: None)
check(ce.read_cia(again).version == info.version + 2 and ctrtool_ok(again)[0], "editing an edited CIA goes up again")
bad = bytearray(open(out, "rb").read())
_, secs = ce._parse_cia(bytes(bad))
h = ce._tmd_layout(secs["tmd"])[0]
struct.pack_into(">H", bad, bytes(bad).find(secs["tmd"]) + h + 0x9C, 0xFFFF)
try:
    ce.edit_cia(bytes(bad), icon=e.icon); check(False, "version 0xFFFF refused")
except ce.EditError as ex:
    check("highest" in str(ex), f"version 0xFFFF refused: {ex}")
check(e.icon[:0x2040] == info.icon[:0x2040], "icon settings/titles bytes untouched")

print("titles only")
out = ce.run(ce.EditJob(cia_path=png_cia, titles=("New Name", "New Long Name", "New Pub")), lambda k, s: None)
e = ce.read_cia(out)
good, *_ = ctrtool_ok(out)
check(good and e.titles == ("New Name", "New Long Name", "New Pub"), f"titles changed: {e.titles}")
check(e.icon[0x2040:] == info.icon[0x2040:] and e.banner == info.banner, "icon picture and banner untouched")
jp = e.icon[8:8 + 0x80].decode("utf-16-le").split("\0")[0]
check(jp == "New Name", "every language slot gets the new title")

print("sound only")
out = ce.run(ce.EditJob(cia_path=png_cia, wav_path=os.path.join("wav", "clip_288.wav")), lambda k, s: None)
e = ce.read_cia(out)
good, *_ = ctrtool_ok(out)
cw = struct.unpack_from("<I", info.banner, 0x84)[0]
check(good and abs(e.sound_seconds - 2.88) < 0.01, f"new sound: {e.sound_seconds} s")
check(e.banner[:0x84] == info.banner[:0x84] and e.banner[0x88:cw] == info.banner[0x88:cw], "banner image untouched")

print("banner only - keeps the sound")
out = ce.run(ce.EditJob(cia_path=glb_cia, banner_mode=pl.MODE_PNG, banner_path="banner256.png"), lambda k, s: None)
e = ce.read_cia(out)
good, *_ = ctrtool_ok(out)
check(good and e.banner != g.banner and ce.banner_cwav(e.banner) == ce.banner_cwav(g.banner),
      "new banner, the CIA's own sound kept byte for byte")

print("everything at once")
out = ce.run(ce.EditJob(cia_path=png_cia, icon_png=icon_png, titles=("All", "All New", "Me"),
                        banner_mode=pl.MODE_GLB, banner_path="test.glb",
                        wav_path=os.path.join("wav", "clip_288.wav")), lambda k, s: None)
e = ce.read_cia(out)
good, files, tid = ctrtool_ok(out)
check(good and tid == "000400000ff3e100" and e.titles == ("All", "All New", "Me")
      and abs(e.sound_seconds - 2.88) < 0.01 and files["banner.bin"] == e.banner, "icon, titles, banner and sound")
check(ce.check_cia(open(out, "rb").read()) == [], "own check passes")

print("refused")
for name, change, want in (
        ("encrypted content", lambda d: d, "encrypted"),
        ("not a CIA", lambda d: b"hello" * 3000, "isn't a CIA")):
    data = bytearray(orig_bytes)
    if name == "encrypted content":
        header, secs = ce._parse_cia(orig_bytes)
        rec, *_ = ce._content0(secs)
        tmd_off = ce._al(0x2020, 64) + ce._al(len(secs["certs"]), 64) + ce._al(len(secs["ticket"]), 64)
        data[tmd_off + rec + 6 + 1] |= 1  # content type: encrypted
    data = change(bytes(data))
    p = os.path.join(W, name.replace(" ", "_") + ".cia")
    open(p, "wb").write(data)
    try:
        ce.read_cia(p); check(False, f"{name} refused")
    except ce.EditError as ex:
        check(want in str(ex), f"{name} refused: {ex}")
check(ce.validate(ce.EditJob(cia_path=png_cia)) == ["Choose at least one thing to change"], "nothing chosen")
check(any("48" in p for p in ce.validate(ce.EditJob(cia_path=png_cia, icon_png="banner256.png"))), "wrong icon size")

print("edit mode in the main window")
import tkinter as tk  # noqa: E402
import yanbf_cbc as gui  # noqa: E402
import cia_edit_page as P  # noqa: E402
root = tk.Tk(); root.withdraw()
app = gui.App(root)
page = P.install(app)
root.deiconify(); root.update()


def pump(secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.02)


check(app.build_btn.winfo_ismapped() and page.side.winfo_ismapped() and not page.frame.winfo_ismapped(),
      "starts in New forwarder mode, as before")
page.show_mode(P.MODE_EDIT); pump()
check(page.frame.winfo_ismapped() and not page.side.winfo_ismapped() and not app.build_btn.winfo_ismapped()
      and page.save_btn.winfo_ismapped() and not app.icon_entry.winfo_ismapped(),
      "Edit existing CIA: editor instead of the form, Save instead of Build")
check(app.log_text.winfo_ismapped() and "Open a CIA" in app.status_var.get(), "log and status stay; status says what's needed")
check(str(page.save_btn.cget("state")) == "disabled", "nothing open -> Save disabled")
page.load(glb_cia); pump()
check("Edit Model" in page.info_label.cget("text") and "000400000ff3e200" in page.info_label.cget("text"),
      "shows the CIA's titles and IDs")
check(not page.on["titles"].get(), "opening a CIA doesn't tick Titles")
page.vars["short"].set("Changed"); pump(0.1)
check(page.on["titles"].get(), "typing a new title ticks Titles")
page.vars["short"].set("Edit Model"); pump(0.1)
check(not page.on["titles"].get(), "typing it back unticks it")

print("drops go to the editor")
app.handle_drop([os.path.join(S, "wav", "ref.wav"), icon_png, os.path.join(S, "banner256.png")], 0, 0)
pump(0.5)
check(page.vars["wav"].get().endswith("ref.wav") and page.on["wav"].get(), ".wav -> Sound, ticked")
check(page.vars["icon"].get() == icon_png and page.on["icon"].get(), "48×48 .png -> Icon picture")
check(page.vars["banner"].get().endswith("banner256.png") and page.banner_mode.get() == pl.MODE_PNG,
      "other .png -> Banner (flat)")
check(app.icon_var.get() == "", "the build form's fields aren't touched")
check("Ready to save" in app.status_var.get() and str(page.save_btn.cget("state")) == "normal", "ready -> Save enabled")

print("saving")
page.save()
end = time.time() + 30
while time.time() < end and not page.saved:
    root.update(); time.sleep(0.05)
check(page.saved and os.path.isfile(page.saved) and "Saved" in app.status_var.get(), f"saved: {page.saved}")
check("EDITED CIA SAVED" in app.log_text.get("1.0", "end"), "logged in the main log")
e = ce.read_cia(page.saved)
good, *_ = ctrtool_ok(page.saved)
check(good and abs(e.sound_seconds - 2.9375) < 0.01, "the saved CIA checks out, with the new sound")
page.send(); root.update()
check(app.ftp_win is not None and app.ftp_win.cia_source() == (page.saved, "chosen"),
      "Send to 3DS… sends the edited CIA")
app.ftp_win.close(); root.update()
page.load(os.path.join(W, "not_a_CIA.cia")); pump()
check("isn't a CIA" in page.info_label.cget("text") and str(page.save_btn.cget("state")) == "disabled",
      "a non-CIA is refused")

print("back to New forwarder")
page.show_mode(P.MODE_NEW); pump()
check(app.build_btn.winfo_ismapped() and page.side.winfo_ismapped() and app.icon_entry.winfo_ismapped()
      and not page.save_btn.winfo_ismapped() and not page.frame.winfo_ismapped(), "form, previews and Build are back")
check("Needs:" in app.status_var.get() and "Open a CIA" not in app.status_var.get(), "status is the build form's again")
app.handle_drop([icon_png], app.icon_entry.winfo_rootx() + 5, app.icon_entry.winfo_rooty() + 5); pump()
check(app.icon_var.get() == icon_png, "drops go to the build form again")
app._on_close()

print("reading the old sound: every CWAV encoding")
import io, math, wave  # noqa: E402,E401
tone = os.path.join(W, "tone.wav")
with wave.open(tone, "wb") as wv:
    wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(32000)
    wv.writeframes(b"".join(struct.pack("<hh", int(12000 * math.sin(2 * math.pi * 440 * i / 32000)),
                                        int(9000 * math.sin(2 * math.pi * 660 * i / 32000))) for i in range(32000)))
with wave.open(tone) as wv:
    ref = struct.unpack(f"<{wv.getnframes() * 2}h", wv.readframes(wv.getnframes()))
for enc, limit in (("pcm16", 1), ("pcm8", 300), ("dspadpcm", 60), ("imaadpcm", 1500)):
    cw = os.path.join(W, f"tone_{enc}.cwav")
    subprocess.run([paths.CWAVTOOL, "-i", tone, "-o", cw, "-e", enc], capture_output=True)
    with wave.open(io.BytesIO(ce.cwav_to_wav(open(cw, "rb").read()))) as wv:
        got = struct.unpack(f"<{wv.getnframes() * wv.getnchannels()}h", wv.readframes(wv.getnframes()))
        ok = wv.getnchannels() == 2 and wv.getframerate() == 32000 and wv.getnframes() >= 32000
    n = min(len(got), len(ref))
    rms = math.sqrt(sum((a - b) ** 2 for a, b in zip(got[:n], ref[:n])) / n)
    check(ok and rms < limit, f"{enc}: decoded, error {rms:.1f} (signal ~7650, limit {limit})")

print("reading the old banner")
td = os.path.join(W, "test files")
os.makedirs(td)
files = {"icon2": os.path.join(td, "test icon 2.png"), pl.MODE_PNG: os.path.join(td, "test banner.png"),
         pl.MODE_GLB: os.path.join(td, "test banner.glb"), "audio": os.path.join(td, "test sound.wav")}
fixtures.orange_icon(files["icon2"])
fixtures.test_banner_png(files[pl.MODE_PNG])
fixtures._banner_glb(files[pl.MODE_GLB])
fixtures.chime_wav(files["audio"])
edit_cia = build(pl.MODE_PNG, files[pl.MODE_PNG], "", "FF3E3", "Editor Test")  # 1 s of silence


def fill_editor(page):
    """The editor test: the flat-banner CIA open, a new icon, the 3D banner and a chime."""
    page.show_mode(P.MODE_EDIT)
    page.load(edit_cia)
    page.vars["icon"].set(files["icon2"])
    page.vars["banner"].set(files[pl.MODE_GLB])
    page.vars["wav"].set(files["audio"])


check(os.path.isfile(edit_cia) and ce.read_cia(edit_cia).title_id == "000400000ff3e300", "test CIA built")
check(ce.banner_source(edit_cia) == (pl.MODE_PNG, os.path.join(os.path.dirname(edit_cia), "input files", "banner_source.png")),
      "a CIA this program built: finds the banner file it was built from")
lone = os.path.join(W, "lone.cia")
shutil.copyfile(edit_cia, lone)
check(ce.banner_source(lone) is None, "a CIA on its own: no source file")
tex = ce.banner_texture(ce.read_cia(lone).banner)
src = Image.open(files[pl.MODE_PNG]).convert("RGBA")
diff = max(abs(a - b) for pa, pb in zip(list(tex.get_flattened_data()), list(src.get_flattened_data()))
           for a, b in zip(pa, pb) if pb[3] == 255)
check(tex.size == (256, 128) and diff <= 17, f"flat banner picture read from the CIA itself, right way up (diff {diff})")
check(ce.banner_texture(ce.read_cia(glb_cia).banner) is None, "an untextured 3D banner has no picture to show")

print("edited CIAs keep the banner source")
out = ce.run(ce.EditJob(cia_path=edit_cia, wav_path=tone), lambda k, s: None)
check(ce.banner_source(out) == (pl.MODE_PNG, os.path.join(os.path.dirname(out), "input files", "banner_source.png")),
      "banner kept -> its source file is copied next to the edited CIA")
out = ce.run(ce.EditJob(cia_path=edit_cia, banner_mode=pl.MODE_GLB, banner_path=files[pl.MODE_GLB]), lambda k, s: None)
check(ce.banner_source(out)[0] == pl.MODE_GLB and not os.path.exists(os.path.join(os.path.dirname(out), "input files",
      "banner_source.png")), "new banner -> its file is saved instead (the old one removed)")

print("Now | New previews")
root = tk.Tk(); root.withdraw()
app = gui.App(root)
page = P.install(app)
root.deiconify(); root.update()
played = []


class FakePlayer:  # (no real sound during the tests)
    def play(self, path): played.append(path)
    def playing(self): return True
    def stop(self): played.append("stop")


page.player = FakePlayer()
fill_editor(page)
end = time.time() + 30
while time.time() < end and not (page.info and page.on["wav"].get()):
    root.update(); time.sleep(0.05)
pump(1)
cap = lambda part, which: page.cells[(part, which)][1].cget("text")
check(page.editing() and page.info.path == edit_cia, "switched to Edit existing CIA with the test CIA open")
check(page.vars["icon"].get() == files["icon2"] and page.vars["banner"].get() == files[pl.MODE_GLB]
      and page.vars["wav"].get() == files["audio"] and all(page.on[k].get() for k in ("icon", "banner", "wav")),
      "new icon, banner and sound filled in and ticked")
check("Ready to save" in app.status_var.get(), "ready to save")
check(cap("icon", "old") == "Editor Test" and cap("icon", "new") == "(new picture)", "icon: now | new")
check("built from" in cap("banner", "old") and cap("banner", "new") == "3D model", f"banner: {cap('banner', 'old')} | 3D model")
check("1.00 s" in cap("wav", "old") and "2.00 s" in cap("wav", "new"), f"sound: {cap('wav', 'old')} | {cap('wav', 'new')}")
page.toggle_play("old"); root.update()
check(played and played[-1] == page.old_wav and page.play_btns["old"].cget("text") == "■ Stop", "Play now's sound")
page.toggle_play("new"); root.update()
check(played[-1] == files["audio"] and page.play_btns["new"].cget("text") == "■ Stop"
      and page.play_btns["old"].cget("text") == "▶ Play", "Play the new sound (the other button resets)")
page.toggle_play("new"); root.update()
check(played[-1] == "stop" and page.play_btns["new"].cget("text") == "▶ Play", "Stop")
page.on["icon"].set(False); page.on["banner"].set(False); page.on["wav"].set(False); page.validate(); pump(0.3)
check(cap("icon", "new") == cap("banner", "new") == cap("wav", "new") == "unchanged", "unticked -> New shows 'unchanged'")
page.load(lone); pump(0.5)
check(cap("banner", "old") == "Flat image (read from the CIA)", "a CIA on its own: the picture read from the CIA")
page.load(glb_cia.replace("Edit Model.cia", "Edit Model.cia")); pump(1)
check("built from" in cap("banner", "old"), "a 3D banner this program built: rendered from its .glb")
nolone = os.path.join(W, "lone3d.cia"); shutil.copyfile(glb_cia, nolone)
page.load(nolone); pump(0.5)
check("can't be drawn" in cap("banner", "old"), "a 3D banner on its own: says it can't be drawn")
page.show_mode(P.MODE_NEW); root.update()
check(played[-1] == "stop" or page._playing is None, "switching back stops any sound")
app._on_close()

print("HOME Menu preview: now vs new, side by side")
import cia_home_compare as hc  # noqa: E402
import home_preview  # noqa: E402
import preview  # noqa: E402
flat = hc.flat_mesh(src)
im = preview.render(flat, size=home_preview.SCREEN, ss=1, background=Image.new("RGB", home_preview.SCREEN, (0, 0, 0)))
blue = im.getpixel((200, 128))
check(blue[2] > 150 and blue[0] < 80, f"a flat banner is drawn on bannertool's rectangle (centre pixel {blue})")
top = next(y for y in range(240) if im.getpixel((200, y)) != (0, 0, 0))
yellow = [y for y in range(240) for x in range(150, 250, 4) if (lambda c: c[0] > 180 and c[1] > 150 and c[2] < 100)(im.getpixel((x, y)))]
check(40 < top < 120 and im.getpixel((200, 20)) == (0, 0, 0) and yellow and min(yellow) > 120,
      f"right way up (the yellow TEST BANNER line is in the lower half: rows {min(yellow or [0])}+), top row {top}")
root = tk.Tk(); root.withdraw()
app = gui.App(root)
page = P.install(app)
page.player = FakePlayer()
root.deiconify(); root.update()
page.show_mode(P.MODE_EDIT); pump(0.2)
check(str(page.home_btn.cget("state")) == "disabled", "button disabled until a CIA is open")
fill_editor(page)
end = time.time() + 30
while time.time() < end and not (page.info and page.on["wav"].get()):
    root.update(); time.sleep(0.05)
pump(0.5)
check(str(page.home_btn.cget("state")) == "normal", "enabled with a CIA open")
page.open_home_preview(); pump(0.2)
w = page.home_win
w.player = FakePlayer()
check(w is not None and w.win.winfo_exists() and w.sides["old"].kind == "flat" and w.sides["new"].kind == "glb",
      "one window: the CIA's flat banner now, the new 3D model")
check(w.captions["old"].cget("text").startswith("Flat image") and w.captions["new"].cget("text") == "3D model",
      "captions say what each side is")
check(w.last_frames["old"].size == w.last_frames["new"].size == w.display, f"two screens at {w.scale}x: {w.display}")
a0 = w.angle
old0, new0 = w.frame("old").tobytes(), w.frame("new").tobytes()
w.angle = a0 + 1.2
check(w.frame("old").tobytes() == old0 and w.frame("new").tobytes() != new0,
      "the new 3D banner spins, the flat one stays still")
w.toggle_pause(); a = w.angle; pump(0.4)
check(abs(w.angle - a) < 1e-9, "Pause stops both")
w.toggle_pause()
w.play("old"); w.play("new")
check(played[-2:] == [page.old_wav, files["audio"]], "each side plays its own sound")
page.on["banner"].set(False); page.validate(); pump(0.3)
check(page.home_win is w and w.captions["new"].cget("text") == "unchanged" and w.sides["new"].kind == "flat",
      "the open preview follows the editor: banner unticked -> New is 'unchanged'")
page.load(nolone); pump(0.5)
check(w.sides["old"].kind == "none" and "can't be drawn" in w.captions["old"].cget("text"),
      "a 3D banner with no .glb: the backdrop and a note")
page.load(glb_cia); pump(0.5)
check(w.sides["old"].kind == "glb" and "built from" in w.captions["old"].cget("text"),
      "a 3D banner this program built: drawn from its .glb")
page.show_mode(P.MODE_NEW); pump(0.2)
check(w.closed, "switching back to New forwarder closes it")
check(not hasattr(app, "home_win") or app.home_win is None, "the generator's own HOME Menu preview isn't involved")
app._on_close()
finish()
