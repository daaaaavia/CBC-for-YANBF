"""Pipeline: in-process pycgfx, stand-in tools (layout, order, failures, warnings),
upload limits, GUI validation state, and real builds checked with ctrtool."""
import os
import subprocess

from _common import FAKE_TOOLS, S, check, finish, isolate
import paths
import pipeline as pl
from PIL import Image

isolate("pipeline")


def run_job(job, tools=None, out_root=None, show=False):
    lines = []
    p = pl.Pipeline(job, lambda t, s: lines.append((t, s)), tools=tools, output_root=out_root)
    ok = p.run()
    if show:
        for t, s in lines:
            if t != "cmd":
                print(f"    [{t}] {s}")
    return ok, lines, p


tools = FAKE_TOOLS

# ---------------------------------------------------------------- 1. pycgfx
print("1. in-process pycgfx")
ok, printed, tb = pl.convert_glb("test.glb", "test.cgfx")
check(ok and os.path.getsize("test.cgfx") > 0, f"test.glb converted ({os.path.getsize('test.cgfx') if ok else tb})")

# ---------------------------------------------------------------- 2. stand-in tools
print("2. pipeline with stand-in tools")
fake_out = os.path.join(S, "fake_out")
base = dict(icon_path="icon48.png", audio_path="", rom_path="/roms/nds/Some Game.nds", title="Test Title",
            publisher="Me", product_code="CTR-H-TEST", unique_id="0xff3f0", minor="2")
d = os.path.join(fake_out, "Some Game")
ok, lines, _ = run_job(pl.BuildJob(banner_mode="glb", banner_path="test.glb", **base), tools, fake_out)
check(ok, "glb mode succeeds")
expected = [os.path.join(*p.split("/")) for p in (
    "Some Game.cia", "input files/banner_source.glb", "input files/icon.png", "input files/silent_fallback.wav",
    "input files/romfs/path.txt", "produced files/audio.cwav", "produced files/banner.bin",
    "produced files/banner.cgfx", "produced files/icon.bin")]
got = sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs)
check(got == sorted(expected), f"output layout {got}")
check(open(os.path.join(d, "input files", "romfs", "path.txt"), "rb").read() == b"sd:/roms/nds/Some Game.nds",
      "path.txt content, no trailing newline")
cmds = [s for t, s in lines if t == "cmd"]
check(any("-DAPP_UNIQUE_ID=0xFF3F0" in c and "-minor 2" in c for c in cmds), "makerom gets 0xFF3F0 / minor 2")
order = [s for t, s in lines if t == "step"]
check([o.split(".")[0][-1] for o in order[2:]] == list("12345"), "step order icon, pycgfx, audio, banner, CIA")

open(os.path.join(d, "stale.txt"), "w").write("x")
ok, lines, _ = run_job(pl.BuildJob(banner_mode="png", banner_path="banner256.png", **base), tools, fake_out)
check(ok, "png mode, same name, succeeds")
check(not os.path.exists(os.path.join(d, "stale.txt")), "rerun overwrote old folder")
check(not os.path.exists(os.path.join(d, "produced files", "banner.cgfx")), "png mode: no banner.cgfx")
check(any("makebanner -i" in s for t, s in lines if t == "cmd"), "png mode uses makebanner -i")

os.environ["FAKE_FAIL"] = "cwavtool"
ok, lines, _ = run_job(pl.BuildJob(banner_mode="png", banner_path="banner256.png", **base), tools, fake_out)
del os.environ["FAKE_FAIL"]
check(not ok, "forced cwavtool failure fails")
check(any(t == "err" and "simulated failure" in s for t, s in lines), "stderr is in the log")
check(not any("makebanner" in s for t, s in lines if t == "cmd"), "pipeline stopped after failing step")
check(lines[-1][0] == "fail" and "Audio" in lines[-1][1], f"fail line names step: {lines[-1][1]}")

m = pl.load_pycgfx()
orig = m.write


def big(c):
    data = orig(c)
    print(f"WARNING: CGFX is too big ({len(data)} bytes, max is 524288 bytes)")
    print("WARNING: other")
    return data


m.write = big
ok, lines, _ = run_job(pl.BuildJob(banner_mode="glb", banner_path="test.glb", **dict(base, rom_path="")), tools, fake_out)
check(ok and ("bigwarn", ) == tuple(t for t, s in lines if "too big" in s), "too-big warning -> bigwarn, build continues")
check(("warn", "WARNING: other") in lines, "other WARNING -> warn")
check(open(os.path.join(fake_out, "Test Title", "input files", "romfs", "path.txt"), "rb").read() == b"",
      "empty ROM path -> empty path.txt in output/<Title>")
check(any(t == "warn" and "won't find the ROM" in s for t, s in lines), "empty ROM path warning")


def boom(c):
    print("partial output")
    raise IndexError("boom")


m.write = boom
ok, lines, _ = run_job(pl.BuildJob(banner_mode="glb", banner_path="test.glb", **base), tools, fake_out)
m.write = orig
i = lines.index(("out", "partial output"))
check(not ok and lines[i + 1][0] == "err" and "IndexError" in lines[i + 1][1], "pycgfx exception: output then red traceback")

check(pl.romfs_path_text("sd:/a/b.nds") == "sd:/a/b.nds", "no double sd:")
check(pl.romfs_path_text(r"roms\nds\x.nds") == "sd:/roms/nds/x.nds", "backslashes + leading /")
check(pl.output_name("", "CON") == "_CON", "reserved name prefixed")
check(pl.output_name("/x/a:b?.nds", "t") == "a_b_", "bad chars replaced")
check(pl.output_name("", " ... ") == "untitled", "empty -> untitled")
check(pl.parse_unique_id("0xFFG3")[1] == "Not hexadecimal: invalid character(s) 'G'", "uid G error")
check(pl.parse_unique_id("1234567")[1] == "Too long: max 6 hex digits (0xFFFFFF)", "uid too long")
check(pl.parse_unique_id("ff3f0")[0] == "0xFF3F0", "uid normalized")

# ---------------------------------------------------------------- 3. limits
print("3. upload limits")
os.makedirs("lim", exist_ok=True)


def png(n, w, h):  # the files are made by fixtures.py; this names them and states their size
    p = os.path.join("lim", n)
    if not os.path.exists(p):
        Image.new("RGBA", (w, h)).save(p)
    return p


cases = [
    (pl.KIND_ICON, png("i48.png", 48, 48), None),
    (pl.KIND_ICON, png("i49.png", 49, 48), "Icon is 49×48 px - must be exactly 48×48 px"),
    (pl.KIND_ICON, png("i48x49.png", 48, 49), "Icon is 48×49 px - must be exactly 48×48 px"),
    (pl.KIND_ICON, png("i47.png", 47, 48), "Icon is 47×48 px - must be exactly 48×48 px"),
    (pl.KIND_ICON, png("i48x47.png", 48, 47), "Icon is 48×47 px - must be exactly 48×48 px"),
    (pl.KIND_ICON, png("i32.png", 32, 32), "Icon is 32×32 px - must be exactly 48×48 px"),
    (pl.KIND_ICON, png("i24.png", 24, 24), "Icon is 24×24 px - must be exactly 48×48 px"),
    (pl.KIND_BANNER_PNG, png("b256.png", 256, 128), None),
    (pl.KIND_BANNER_PNG, png("b257.png", 257, 128), "Banner image is 257×128 px - must be at most 256×128 px"),
    (pl.KIND_BANNER_PNG, png("b129.png", 256, 129), "Banner image is 256×129 px - must be at most 256×128 px"),
    (pl.KIND_ICON, "lim/jpeg.png", "Icon must be a PNG (this file is JPEG)"),
    (pl.KIND_ICON, "lim/junk.png", "junk.png is not a readable image file"),
    (pl.KIND_GLB, "lim/m_ok.glb", None),
    (pl.KIND_GLB, "lim/m_old.glb", None),
    (pl.KIND_GLB, "lim/m_big.glb", "Model is 524,289 bytes (512.0 KB) - must be at most 524,288 bytes (512 KB)"),
    (pl.KIND_GLB, "lim/nope.glb", "File not found"),
]
for kind, p, want in cases:
    got = pl.check_input_file(kind, p)
    check(got == want, f"{os.path.basename(p)}: {got!r}".encode("ascii", "replace").decode())
cached = os.path.join("lim", "cache_test.png")
Image.new("RGBA", (48, 48)).save(cached)
check(pl.check_input_file(pl.KIND_ICON, cached) is None, "48x48 accepted (and cached)")
Image.new("RGBA", (60, 60)).save(cached)
os.utime(cached, (1, 1))
check((pl.check_input_file(pl.KIND_ICON, cached) or "").startswith("Icon is 60"), "cache invalidated on change")

# ---------------------------------------------------------------- 4. GUI state
print("4. GUI state (headless)")
import tkinter as tk
import yanbf_cbc as g

root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()
st = lambda: (str(app.build_btn["state"]), app.status_var.get())
check(st()[0] == "disabled" and st()[1].startswith("Needs: icon"), f"initial {st()}")
app.icon_var.set(os.path.join(S, "lim", "i49.png")); root.update()
check(app.icon_entry["bg"] == g.ERR_BG and "49×48" in app.icon_err["text"], "bad icon: red field + message")
app.icon_var.set(os.path.join(S, "icon48.png"))
app.banner_var.set(os.path.join(S, "test.glb"))
app.title_var.set("T"); app.product_var.set("CTR-H-TEST"); app.uid_var.set("0xFG"); root.update()
check(st()[0] == "disabled" and "'G'" in app.uid_err["text"] and app.uid_entry["bg"] == g.ERR_BG, "bad uid blocks build")
app.uid_var.set("1234567"); root.update()
check("Too long" in app.uid_err["text"], "long uid message")
app.uid_var.set("ff3f0"); root.update()
check(st() == ("normal", "Ready"), f"valid form -> {st()}")
app.minor_var.set("64"); root.update()
check(st()[0] == "disabled" and app.minor_err["text"], "minor 64 blocked")
app.minor_var.set("63"); root.update()
check(st()[0] == "normal", "minor 63 ok")
app.mode_var.set(pl.MODE_PNG); root.update()
check(app.banner_var.get() == "" and "256×128" in app.banner_caption_var.get() and st()[0] == "disabled",
      "mode switch clears .glb and changes caption")
app.banner_var.set(os.path.join(S, "lim", "b257.png")); root.update()
check("257×128" in app.banner_err["text"], "oversize banner message")
app.banner_var.set(os.path.join(S, "banner256.png")); root.update()
check(st()[0] == "normal", "valid png banner")
app.audio_var.set(os.path.join(S, "nope.wav")); root.update()
check(st()[0] == "disabled" and app.audio_err["text"] == "File not found", "missing audio blocks")
app.audio_var.set(""); root.update()
app.missing = ["x"]; app.validate()
check(st()[0] == "disabled" and "required tools" in st()[1], "missing tools blocks build")
app.missing = []; app.validate()
root.destroy()

# ---------------------------------------------------------------- 5. real tools
print("5. real tools")
real_out = os.path.join(S, "real_out")
for mode, banner in (("glb", "test.glb"), ("png", "banner256.png")):
    job = pl.BuildJob(icon_path="icon48.png", banner_mode=mode, banner_path=banner, audio_path="",
                      rom_path=f"/roms/nds/Real {mode}.nds", title="Real Test", publisher="YANBF-CBC",
                      product_code="CTR-H-TEST", unique_id="FF3F0", minor=0)
    ok, lines, p = run_job(job, out_root=real_out)
    if not ok:
        for t, s in lines:
            print(f"    [{t}] {s}")
    check(ok and os.path.isfile(p.cia_path), f"real {mode} build -> {p.cia_path and os.path.getsize(p.cia_path)} bytes")
    if ok:
        r = subprocess.run([paths.CTRTOOL, "-i", p.cia_path], capture_output=True, text=True, errors="replace")
        info = r.stdout + r.stderr
        check("000400000ff3f000" in info.lower(), "ctrtool title id 000400000ff3f000")
        check("CTR-H-TEST" in info, "ctrtool product code CTR-H-TEST")

finish()
