# Agent YouTube Shorts dyal Ad3iya (0 dh)

L-agent kaysayeb **3 shorts f nhar** (08:07, 14:07, 20:07 wa9t Dubai), kol wa7d fih du3a/dhikr mkhtalef (sawt 3arbi, 4 tsawer AI dyal nfs l-character, zoom animation, sous-titres) w kaylou7o f la chaîne. Kolchi kaykhdem f GitHub, ya3ni l-PC dyalek ykoun tafi.

## Chno kayn f had l-dossier
| Fichier | Chno kaydir |
|---|---|
| `adhkar.json` | 43 du3a/dhikr sa7i7in m3a l-masdar. Zid fih li bghiti (b nfs chkl). |
| `config.json` | Sawt, character, scènes, wa9t, public/private... |
| `generate.py` | Kaysayeb l-video `out/short.mp4` |
| `upload.py` | Kaylou7ha f YouTube |
| `get_token.py` | Kat-runih **mra wa7da** f PC dyalek bach t-connecti la chaîne |
| `.github/workflows/daily-short.yml` | Kaytlanca 3 merrat f nhar |
| `assets/music/` | (Ikhtiyari) 7et hna mp3 bla copyright, l-agent kayzidha b sawt khfif |

---

## Étape 1: GitHub (mjani)
1. Dir compte f github.com.
2. **New repository**, smih b7al `dua-shorts`, w khtar **Private**.
3. **Add file > Upload files**, w 7et ga3 les fichiers dyal had l-dossier.
   Dossier `.github` ma kaytla3ch dima b drag & drop. Ila ma tla3ch, dir **Add file > Create new file**, kteb smiya `.github/workflows/daily-short.yml` w colli fih l-contenu dyalo.

## Étape 2: Tsawer AI (mjani)
L-agent kayjarreb 2 dial services b had tartib:
- **Cloudflare Workers AI** (kayn quota mjani kol nhar, howa li ansa7ek bih):
  1. Dir compte f dash.cloudflare.com.
  2. **Account ID** kayban f la page Workers & Pages (jiha limen).
  3. Mchi l **My Profile > API Tokens > Create Token**, khtar template **"Workers AI"**, w copi token.
- **Pollinations**: mjani bla compte. Kaykhdem automatiquement ila Cloudflare ma khdmch.

## Étape 3: YouTube API (mjani)
1. Mchi l console.cloud.google.com w dir **New Project**.
2. **APIs & Services > Library**, 9leb 3la **YouTube Data API v3** w dir **Enable**.
3. **OAuth consent screen**: khtar External, 3mmer smiya w l-email dyalek. Mn b3d **Publish app** (khass ykoun "In production", sinon token kaymout mn b3d 7 iyam).
4. **Credentials > Create credentials > OAuth client ID**, type **Desktop app**, w telechargi JSON (smih `client_secret.json`).
5. F PC dyalek (mra wa7da), ila 3ndek Python:
   ```
   pip install google-auth-oauthlib
   python get_token.py client_secret.json
   ```
   Ghadi yt7el navigateur. Khtar l-compte dyal la chaîne, w ila ban lik "Google hasn't verified this app", dir Advanced > Continue. Ghadi ytb3o lik 3 dial valeurs.

## Étape 4: Secrets f GitHub
Repo > **Settings > Secrets and variables > Actions > New repository secret**:

| Smiya | Valeur |
|---|---|
| `YT_CLIENT_ID` | mn get_token.py |
| `YT_CLIENT_SECRET` | mn get_token.py |
| `YT_REFRESH_TOKEN` | mn get_token.py |
| `CF_ACCOUNT_ID` | Cloudflare |
| `CF_API_TOKEN` | Cloudflare |

## Étape 5: Test
Repo > **Actions** > "Daily dua short" > **Run workflow**. Mn b3d 3 7ta 6 d9ay9 kat9der tchouf l-video f **Artifacts** w f la chaîne.
Mn hna l-foq kaykhdem bohdo kol nhar.

---

## ⚠️ Bach ytla3o direct PUBLIC
L-agent deja m-configuré 3la `"privacy": "public"`. Walakin YouTube kayrdd ga3 les vidéos li tlou7o b API **private** 7ta Google tverifi l-projet dyalek (audit). Hadi 9a3ida dyal YouTube, w ma kaynach tari9a s7i7a bach tdouz menha.

**Dir l-audit merra wa7da (mjani):**
1. 9leb f Google 3la **"YouTube API Services Audit and Quota Extension Form"** w 3mmro.
2. Chra7 b 9lil dyal l-klam: "Personal app that uploads my own original Shorts to my own channel. No other users." 7et lien dyal la chaîne.
3. Ila tlbo lik **Privacy Policy** w **Terms**, kat9der tdir page sghira mjaniya (Google Sites) fiha jumla wa7da: had l-app ma katjma3 7ta data.
4. Tsenna jawab (ymken chi iyam wla simanat).

Mlli y-approuviw, les vidéos ghadi ytla3o public direct, bla ma tbeddel 7ta 7aja f l-code.
**Tal dak l-wa9t**: l-agent kaylou7 3 f nhar private, w nta dkhol l YouTube Studio f telephone w beddelhoum l Public (taqriban 30 seconde f nhar).

## Bdel chi 7aja
- **Ch7al dial videos f nhar / wa9t**: beddel stour `cron` f `daily-short.yml` (wa9t b UTC = Dubai na9es 4 sa3at). Max ~6/nhar (quota YouTube).
- **Sawt dyal mra**: `"voice": "ar-SA-ZariyahNeural"` f config.json (kayn 7ta `ar-EG-SalmaNeural`, `ar-MA-JamalNeural`...).
- **Character**: beddel `character` f config.json (ex: bent b l-hijab, wlad, chibani...).
- **Zid du3a**: zid bloc jdid f `adhkar.json`. Dima 7et du3a sa7i7a m3a masdarha.

## Nsa2i7
- **Sm3 l-videos lowlin**: TTS ymken ygholet f chi kelma. Ila l9iti chi ghalat, zid tachkil f dik l-kelma f `adhkar.json`.
- **Ma tst3melch musique/sawt dyal 9nawat khrin**: copyright.
- Ila bghiti l-qualité dyal l-video li sifti (animation 3D w lip-sync), hadik khassha AI video b lflous (Kling/Veo). Ila bdat la chaîne katdekhkhel, kanbeddlo `generate.py` w ykhdem bih.
