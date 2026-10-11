"""Run ONCE on your own computer to get the YouTube refresh token.

  pip install google-auth-oauthlib
  python get_token.py client_secret.json

A browser opens -> choose the Google account that owns the channel -> allow.
Copy the 3 printed values into your GitHub repo secrets.
"""
import json, sys
from google_auth_oauthlib.flow import InstalledAppFlow

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, ["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
info = json.load(open(path))
info = info.get("installed") or info.get("web")
print("\nYT_CLIENT_ID     =", info["client_id"])
print("YT_CLIENT_SECRET =", info["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
