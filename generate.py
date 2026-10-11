"""Generate one vertical Short (1080x1920) for free, from the content file set in config.json.

Content entries (stories.json / adhkar.json):
  {"id", "title", "lines": [narration...], optional "scenes": [image prompts with {character} keys],
   optional "theme", "moral", "source", "repeat"}
When every entry has been used once, new stories are written by a free AI (Cloudflare Workers AI)
and appended to the content file; if that fails, the list starts again from the beginning.

Usage:
  python generate.py              # normal run
  python generate.py --offline    # no internet: placeholder images + silent audio (for testing)
  python generate.py --id NAME    # force a specific entry
"""
import argparse, base64, json, os, random, re, shutil, subprocess, sys, time, urllib.parse
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


# ---------------------------------------------------------------- AI story writer (free)
def cf_llm(messages, cfg):
    acct, token = os.getenv("CF_ACCOUNT_ID"), os.getenv("CF_API_TOKEN")
    if not (acct and token):
        return None
    import requests
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{cfg['story_ai']['model']}"
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                      json={"messages": messages, "max_tokens": 1500, "temperature": 0.9}, timeout=120)
    if r.status_code != 200:
        print("llm:", r.status_code, r.text[:200]); return None
    res = r.json().get("result", {}).get("response")
    return res if isinstance(res, str) else json.dumps(res)


def write_new_story(content, cfg):
    ai = cfg.get("story_ai")
    if not ai:
        return None
    chars = list(cfg["characters"].keys())
    used = [c["title"] for c in content][-60:]
    prompt = ai["prompt"].format(characters=", ".join("{" + c + "}" for c in chars),
                                 used=" | ".join(used), theme=random.choice(ai["themes"]))
    for attempt in range(3):
        txt = cf_llm([{"role": "system", "content": ai["system"]}, {"role": "user", "content": prompt}], cfg)
        if not txt:
            continue
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            s = json.loads(m.group(0))
            lines = [str(x).strip() for x in s["lines"] if str(x).strip()]
            scenes = [str(x).strip() for x in s["scenes"] if str(x).strip()]
            assert 6 <= len(lines) <= 12 and 3 <= len(scenes) <= 6 and s["title"].strip()
            assert all(re.search(r"\{(" + "|".join(chars) + r")\}", sc) for sc in scenes)
            assert all(c not in sc for sc in scenes for c in "[]<>")
            words = " ".join(lines).lower()
            assert not any(b in words for b in ai["banned_words"])
            story = {"id": "ai_" + re.sub(r"[^a-z0-9]+", "_", s["title"].lower()).strip("_")[:40] + f"_{len(content)}",
                     "title": s["title"].strip()[:80], "theme": s.get("theme", "moral"),
                     "moral": str(s.get("moral", "")).strip(), "lines": lines, "scenes": scenes, "ai": True}
            print("AI wrote a new story:", story["title"])
            return story
        except Exception as e:
            print("story rejected:", e)
    return None


# ---------------------------------------------------------------- choose
def pick(content, state, cfg, force_id, content_p, offline):
    if force_id:
        return next(d for d in content if d["id"] == force_id)
    i = state.get("next_index", 0)
    if i >= len(content):
        new = None if offline else write_new_story(content, cfg)
        if new:
            content.append(new)
            content_p.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
            i = len(content) - 1
        else:
            i = i % len(content)
            state["cycle"] = state.get("cycle", 0) + 1
    state["next_index"] = i + 1
    state["count"] = state.get("count", 0) + 1
    return content[i]


# ---------------------------------------------------------------- voice
def tts(text, path, cfg, offline):
    if offline:
        secs = max(1.2, len(text) * 0.06)
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
                      json={"prompt": prompt, "steps": 6}, timeout=120)
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
    colors = ["0x2b1d2e", "0x3a2a1a", "0x1d2b3a", "0x2e2a1d", "0x1d3a2b", "0x3a1d2b"]
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"color=c={colors[i % len(colors)]}:s={W}x{H}", "-vf", "vignette=PI/4", "-frames:v", "1", str(path)])


def image_prompts(entry, cfg, seed):
    chars = cfg.get("characters", {})
    if entry.get("scenes"):
        out = []
        for sc in entry["scenes"]:
            for k, v in chars.items():
                sc = sc.replace("{" + k + "}", v)
            out.append(f"{sc}. {cfg['style']}")
        return out
    # older format (duas): one character + scene + mood progression
    n = max(1, min(cfg["images_per_video"], len(entry["lines"])))
    scene = random.Random(seed).choice(cfg["scenes"])
    moods = cfg["moods"].get(entry.get("theme"), list(cfg["moods"].values())[0])
    return [f"{cfg['character']}, {scene}, {moods[min(i * len(moods) // n, len(moods) - 1)]}. {cfg['style']}"
            for i in range(n)]


def make_images(prompts, cfg, seed, offline):
    paths = []
    for i, prompt in enumerate(prompts):
        p = TMP / f"img_{i}.jpg"
        ok = False
        if not offline:
            for prov in cfg["image_providers"]:
                for attempt in range(3):
                    try:
                        fn = img_cloudflare if prov == "cloudflare" else img_pollinations
                        ok = fn(prompt, seed + i, p)
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


def ass_escape(s):
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def write_ass(path, title, cues, total, cfg):
    sub = cfg["subtitles"]
    outro = cfg["outro_seconds"]
    f = sub["font"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{f},{sub['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,6,3,{sub['alignment']},80,80,{sub['margin_v']},1
Style: Title,{f},{sub['title_size']},&H0000E5FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,2,8,70,70,200,1
Style: Outro,{f},{sub['size'] - 8},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,2,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if sub.get("show_title", True):
        ev.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total - outro)},Title,,0,0,0,,{{\\fad(300,300)}}{ass_escape(title)}")
    for start, end, text in cues:
        ev.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Main,,0,0,0,,{{\\fad(120,120)}}{ass_escape(text)}")
    ev.append(f"Dialogue: 1,{ass_time(total - outro)},{ass_time(total)},Outro,,0,0,0,,{{\\fad(300,0)}}{ass_escape(cfg['outro_text'])}")
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def strip_emoji(s):
    return re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", s).strip()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--no-state", action="store_true", help="don't advance state.json")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    content_p = ROOT / cfg.get("content_file", "adhkar.json")
    content = json.loads(content_p.read_text(encoding="utf-8"))
    state_p = ROOT / "state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    if state.get("content_file") != content_p.name:      # switched content -> start from the top
        state = {"content_file": content_p.name}

    entry = pick(content, state, cfg, a.id, content_p, a.offline)
    seed = int(date.today().strftime("%Y%m%d")) * 10 + state.get("count", 0) * 7919
    print("Entry:", entry["id"], "seed:", seed)

    shutil.rmtree(OUT, ignore_errors=True); TMP.mkdir(parents=True)
    lines = entry["lines"] * entry.get("repeat", 1)

    # 1) voice per line, with a pause after each
    pause = cfg["pause_between_lines"]
    cues, seg_files, t = [], [], 0.4
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
    prompts = image_prompts(entry, cfg, seed)
    n = len(prompts)
    imgs = make_images(prompts, cfg, seed, a.offline)
    bounds = [cues[min(len(cues) - 1, k * len(cues) // n)][0] for k in range(n)] + [total]
    bounds[0] = 0.0

    # 3) animated clip per image (slow zoom in / out alternating)
    clips = []
    zoom = cfg.get("zoom", 0.12)
    for k, img in enumerate(imgs):
        d = bounds[k + 1] - bounds[k]
        frames = max(1, round(d * FPS))
        z = f"1+{zoom}*on/{frames}" if k % 2 == 0 else f"{1 + zoom}-{zoom}*on/{frames}"
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
              f"vignette=PI/6,fade=t=in:st=0:d=0.3,fade=t=out:st={max(0, d-0.3):.2f}:d=0.3,format=yuv420p")
        c = TMP / f"clip_{k}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(img), "-vf", vf, "-frames:v", str(frames),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(c)])
        clips.append(c)
    (TMP / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    silent = TMP / "silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(TMP / "clips.txt"), "-c", "copy", str(silent)])

    # 4) subtitles + audio (+ optional royalty-free background music in assets/music)
    ass = TMP / "subs.ass"
    write_ass(ass, strip_emoji(entry["title"]), cues, total, cfg)
    music = sorted((ROOT / "assets" / "music").glob("*.mp3")) if (ROOT / "assets" / "music").exists() else []
    out = OUT / "short.mp4"
    fontsdir = ROOT / "assets" / "fonts"
    sub_filter = f"subtitles={ass.name}" + (f":fontsdir={fontsdir}" if fontsdir.exists() else "")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.Random(seed).choice(music))]
        af = (f"[1:a]apad,atrim=0:{total:.2f},volume=1.0[v];[2:a]atrim=0:{total:.2f},volume=0.10,"
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
    vals = {"title": entry["title"], "story": "\n".join(entry["lines"]),
            "moral": entry.get("moral", ""), "source": entry.get("source", ""),
            "outro": cfg["outro_text"], "hashtags": " ".join(yt["hashtags"])}
    meta = {
        "title": yt["title_template"].format(**vals)[:100],
        "description": yt["description_template"].format(**vals)[:4900],
        "tags": yt["tags"],
        "entry_id": entry["id"],
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if not a.no_state and not a.id:
        state_p.write_text(json.dumps(state, indent=2))
    print(f"OK -> {out} ({total:.1f}s)")


if __name__ == "__main__":
    main()
