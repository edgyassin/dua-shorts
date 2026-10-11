"""Generate one vertical dua/adhkar Short (1080x1920) for free.

Pipeline: pick next dhikr -> Arabic voice (edge-tts) -> 4 AI images
(Cloudflare Workers AI free tier or Pollinations) -> zoom animation,
Arabic subtitles, fades (ffmpeg) -> out/short.mp4 + out/meta.json

Usage:
  python generate.py              # normal run
  python generate.py --offline    # no internet: placeholder images + silent audio (for testing)
  python generate.py --id shifa   # force a specific dhikr
"""
import argparse, base64, json, os, random, shutil, subprocess, sys, time, urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
TMP = OUT / "tmp"
W, H, FPS = 1080, 1920, 30


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Command failed: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(path)]).strip())


# ---------------------------------------------------------------- choose
def pick(adhkar, state, force_id=None):
    if force_id:
        return next(d for d in adhkar if d["id"] == force_id), state
    i = state.get("next_index", 0) % len(adhkar)
    state["next_index"] = i + 1
    state["cycle"] = state.get("cycle", 0) + (1 if i + 1 >= len(adhkar) else 0)
    state["count"] = state.get("count", 0) + 1
    return adhkar[i], state


# ---------------------------------------------------------------- voice
def tts(text, path, cfg, offline):
    if offline:
        secs = max(1.2, len(text) * 0.085)
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{secs:.2f}", str(path)])
        return
    import asyncio, edge_tts
    for attempt in range(4):
        try:
            asyncio.run(edge_tts.Communicate(text, cfg["voice"], rate=cfg["voice_rate"]).save(str(path)))
            if path.exists() and path.stat().st_size > 1000:
                return
        except Exception as e:  # network hiccup
            print("tts retry:", e)
        time.sleep(3 * (attempt + 1))
    sys.exit("TTS failed")


# ---------------------------------------------------------------- images
def img_cloudflare(prompt, seed, path):
    acct, token = os.getenv("CF_ACCOUNT_ID"), os.getenv("CF_API_TOKEN")
    if not (acct and token):
        return False
    import requests
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                      json={"prompt": prompt, "steps": 6, "seed": seed}, timeout=120)
    if r.status_code != 200:
        print("cloudflare:", r.status_code, r.text[:200]); return False
    path.write_bytes(base64.b64decode(r.json()["result"]["image"]))
    return True


def img_pollinations(prompt, seed, path):
    import requests
    q = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{q}?width=768&height=1344&seed={seed}&model=flux&nologo=true"
    headers = {}
    if os.getenv("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('POLLINATIONS_TOKEN')}"
    r = requests.get(url, headers=headers, timeout=180)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        print("pollinations:", r.status_code); return False
    path.write_bytes(r.content)
    return True


def img_placeholder(i, path):
    colors = ["0x2b1d2e", "0x3a2a1a", "0x1d2b3a", "0x2e2a1d"]
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"color=c={colors[i % 4]}:s={W}x{H}", "-vf", "vignette=PI/4", "-frames:v", "1", str(path)])


def make_images(n, dhikr, cfg, seed, offline):
    scene = random.Random(seed).choice(cfg["scenes"])
    moods = cfg["moods"].get(dhikr.get("theme"), cfg["moods"]["relief"])
    paths = []
    for i in range(n):
        mood = moods[min(i * len(moods) // n, len(moods) - 1)]
        prompt = f"{cfg['character']}, {scene}, {mood}. {cfg['style']}"
        p = TMP / f"img_{i}.jpg"
        ok = False
        if not offline:
            for prov in cfg["image_providers"]:
                for attempt in range(3):
                    try:
                        fn = img_cloudflare if prov == "cloudflare" else img_pollinations
                        ok = fn(prompt, seed, p)
                    except Exception as e:
                        print(prov, "error:", e); ok = False
                    if ok or prov == "cloudflare" and not os.getenv("CF_API_TOKEN"):
                        break
                    time.sleep(5 * (attempt + 1))
                if ok:
                    break
        if not ok:
            if not offline:
                sys.exit("All image providers failed")
            img_placeholder(i, p)
        paths.append(p)
    return paths


# ---------------------------------------------------------------- subtitles
def ass_time(t):
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(path, title, cues, total, outro):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Amiri,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,3,5,90,90,0,1
Style: Title,Amiri,64,&H00B4F0FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,4,2,8,80,80,230,1
Style: Outro,Amiri,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,4,2,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 0,{ass_time(0)},{ass_time(total - outro)},Title,,0,0,0,,{{\\fad(300,300)}}{title}"]
    for start, end, text in cues:
        ev.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Main,,0,0,0,,{{\\fad(150,150)}}{text}")
    ev.append(f"Dialogue: 1,{ass_time(total - outro)},{ass_time(total)},Outro,,0,0,0,,{{\\fad(300,0)}}{CFG['outro_text']}")
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main
def main():
    global CFG
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--no-state", action="store_true", help="don't advance state.json")
    a = ap.parse_args()

    CFG = cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    adhkar = json.loads((ROOT / "adhkar.json").read_text(encoding="utf-8"))
    state_p = ROOT / "state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}

    dhikr, state = pick(adhkar, state, a.id)
    # different seed for every video (3 per day -> 3 different scenes/images)
    seed = int(date.today().strftime("%Y%m%d")) * 10 + state.get("count", 0) * 7919
    print("Dhikr:", dhikr["id"], "seed:", seed)

    shutil.rmtree(OUT, ignore_errors=True); TMP.mkdir(parents=True)
    lines = dhikr["lines"] * dhikr.get("repeat", 1)

    # 1) voice per line, with a pause after each
    pause = cfg["pause_between_lines"]
    cues, seg_files, t = [], [], 0.4  # small lead-in
    lead = TMP / "lead.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.4", str(lead)])
    seg_files.append(lead)
    for i, line in enumerate(lines):
        raw = TMP / f"v_{i}.mp3"; wav = TMP / f"v_{i}.wav"
        tts(line, raw, cfg, a.offline)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ar", "24000", "-ac", "1",
             "-af", f"apad=pad_dur={pause}", str(wav)])
        d = duration(wav)
        cues.append((t, t + d - 0.05, line)); t += d
        seg_files.append(wav)
    (TMP / "voice.txt").write_text("".join(f"file '{p.name}'\n" for p in seg_files))
    voice = TMP / "voice.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(TMP / "voice.txt"), str(voice)])
    outro = cfg["outro_seconds"]
    total = t + outro

    # 2) images, spread evenly over the voice part
    n = max(1, min(cfg["images_per_video"], len(lines)))
    imgs = make_images(n, dhikr, cfg, seed, a.offline)
    bounds = [cues[min(len(cues) - 1, k * len(cues) // n)][0] for k in range(n)] + [total]
    bounds[0] = 0.0

    # 3) animated clip per image (slow zoom in / out alternating)
    clips = []
    for k, img in enumerate(imgs):
        d = bounds[k + 1] - bounds[k]
        frames = max(1, round(d * FPS))
        z = f"1+0.12*on/{frames}" if k % 2 == 0 else f"1.12-0.12*on/{frames}"
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
              f"vignette=PI/5,fade=t=in:st=0:d=0.35,fade=t=out:st={max(0, d-0.35):.2f}:d=0.35,format=yuv420p")
        c = TMP / f"clip_{k}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(img), "-vf", vf, "-frames:v", str(frames),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(c)])
        clips.append(c)
    (TMP / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    silent = TMP / "silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(TMP / "clips.txt"), "-c", "copy", str(silent)])

    # 4) subtitles + audio (+ optional royalty-free background music in assets/music)
    ass = TMP / "subs.ass"
    write_ass(ass, dhikr["title"], cues, total, outro)
    music = sorted((ROOT / "assets" / "music").glob("*.mp3")) if (ROOT / "assets" / "music").exists() else []
    out = OUT / "short.mp4"
    fontsdir = ROOT / "assets" / "fonts"
    sub_filter = f"subtitles={ass.name}" + (f":fontsdir={fontsdir}" if fontsdir.exists() else "")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.Random(seed).choice(music))]
        af = (f"[1:a]apad,atrim=0:{total:.2f},volume=1.0[v];[2:a]atrim=0:{total:.2f},volume=0.12,"
              f"afade=t=out:st={total-1.5:.2f}:d=1.5[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        af = f"[1:a]apad,atrim=0:{total:.2f}[a]"
    cmd += ["-filter_complex", f"[0:v]{sub_filter}[vv];{af}", "-map", "[vv]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
            "-ar", "44100", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, cwd=TMP, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr[-2000:])

    # 5) metadata for upload
    yt = cfg["youtube"]
    full = "\n".join(dhikr["lines"])
    rep = f"\n(تُقال {dhikr['repeat']} مرات)" if dhikr.get("repeat") else ""
    meta = {
        "title": f"{dhikr['title']} 🤍 #shorts"[:100],
        "description": f"{full}{rep}\n\n📖 المصدر: {dhikr['source']}\n\n{cfg['outro_text']} 🤍\n\n" + " ".join(yt["hashtags"]),
        "tags": ["دعاء", "اذكار", "رقية شرعية", "ذكر", "اسلام", "dua", "adhkar", "shorts"],
        "dhikr_id": dhikr["id"],
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if not a.no_state and not a.id:
        state_p.write_text(json.dumps(state, indent=2))
    print(f"OK -> {out} ({total:.1f}s)")


if __name__ == "__main__":
    main()
