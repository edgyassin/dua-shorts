"""Upload out/short.mp4 to YouTube using a stored OAuth refresh token.

Env vars (GitHub secrets): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
import json, os, sys, time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["youtube"]
    meta = json.loads((ROOT / "out" / "meta.json").read_text(encoding="utf-8"))
    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        if not os.getenv(k):
            sys.exit(f"Missing secret {k}")

    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                    "categoryId": cfg["category_id"], "defaultLanguage": "ar", "defaultAudioLanguage": "ar"},
        "status": {"privacyStatus": cfg["privacy"], "selfDeclaredMadeForKids": cfg["made_for_kids"],
                   "containsSyntheticMedia": cfg["contains_synthetic_media"]},
    }
    media = MediaFileUpload(str(ROOT / "out" / "short.mp4"), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    resp, tries = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"upload {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tries < 5:
                tries += 1; time.sleep(5 * tries); continue
            raise
    print("Uploaded: https://youtube.com/shorts/" + resp["id"])
    print("privacy:", resp.get("status", {}).get("privacyStatus"))


if __name__ == "__main__":
    main()
