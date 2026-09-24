"""Audio length limit: exactly the length of the reference clip (2.9375 s = 141,000 frames at
48 kHz). wav/ref.wav (fixtures.py) has exactly that length."""
import os
import wave

from _common import REF_WAV, check, finish, isolate, S
isolate("audio")
import pipeline as pl

REF = REF_WAV


def silent(name, frames, rate, channels=2, width=2):
    p = os.path.join(S, "wav", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with wave.open(p, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\0" * frames * channels * width)
    return p


A = pl.KIND_AUDIO
check(pl.check_input_file(A, REF) is None, "reference clip itself (2.9375 s) is allowed")
e = pl.check_input_file(A, silent("ref_plus1.wav", 141001, 48000))
check(e == "Audio is 2.93752 s long - must be at most 2.9375 s", f"one sample over at 48 kHz: {e}")
check(pl.check_input_file(A, silent("exact_32k.wav", 94000, 32000)) is None, "exactly 2.9375 s at 32 kHz allowed")
check(pl.check_input_file(A, silent("under_441.wav", 129543, 44100, 1)) is None, "44.1 kHz 129543 frames (2.93748 s) allowed")
e = pl.check_input_file(A, silent("over_441.wav", 129544, 44100, 1))
check(e == "Audio is 2.937505 s long - must be at most 2.9375 s", f"44.1 kHz one frame over (2.9375056 s): {e}")
e = pl.check_input_file(A, silent("long.wav", 48000 * 5, 48000))
check(e == "Audio is 5 s long - must be at most 2.9375 s", f"5 s clip: {e}")
e = pl.check_input_file(A, silent("long2.wav", int(48000 * 3.2), 48000))
check(e == "Audio is 3.2 s long - must be at most 2.9375 s", f"3.2 s clip: {e}")
e = pl.check_input_file(A, os.path.join(S, "wav", "junk.wav"))
check(e is not None and e.startswith("Can't read this WAV"), f"junk wav: {e}")
check(pl.check_input_file(A, os.path.join(S, "wav", "missing.wav")) == "File not found", "missing file")
check(pl.check_input_file(A, os.path.join(S, "wav", "clip_288.wav")) is None, "a 2.88 s clip is allowed")

print("pipeline + GUI")
job = pl.BuildJob(icon_path="icon48.png", banner_mode="png", banner_path="banner256.png",
                  audio_path=os.path.join(S, "wav", "long.wav"), rom_path="", title="T", publisher="",
                  product_code="CTR-H-TEST", unique_id="FF400", minor=0)
check(pl.validate_job(job) == ["Audio: Audio is 5 s long - must be at most 2.9375 s"], "pipeline rejects long audio")
job.audio_path = REF
check(pl.validate_job(job) == [], "pipeline accepts the reference clip")

import tkinter as tk
import yanbf_cbc as g
root = tk.Tk(); root.withdraw()
app = g.App(root)
app.icon_var.set(os.path.join(S, "icon48.png")); app.mode_var.set(pl.MODE_PNG)
app.banner_var.set(os.path.join(S, "banner256.png"))
app.title_var.set("T"); app.product_var.set("CTR-H-TEST"); app.uid_var.set("FF400")
app.audio_var.set(os.path.join(S, "wav", "ref_plus1.wav")); root.update()
st = (str(app.build_btn["state"]), app.status_var.get())
check(st == ("disabled", "Needs: audio") and app.audio_err["text"].startswith("Audio is 2.93752 s")
      and app.audio_entry["bg"] == g.ERR_BG, f"GUI blocks one-sample-over clip: {st}")
app.audio_var.set(REF); root.update()
check(str(app.build_btn["state"]) == "normal" and app.audio_err["text"] == "", "GUI accepts the reference clip")
check("at most 2.9375 s" in g.CAPTIONS["audio"], "caption states the limit")
root.destroy()

finish()
