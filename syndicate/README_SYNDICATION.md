# 🔐 CYBERDUDEBIVASH SENTINEL SYNDICATION ENGINE v1.0
## RSS → Multi-Platform Social Media Automation | 100% Free | GitHub Actions

This is an optional RSS syndication engine for explicitly configured, supported destinations. Twitter/X and Tumblr are retired distribution channels. Deployment, scheduling, and successful provider dispatch must be verified independently.

---

## 📋 PLATFORMS SUPPORTED

| Platform | API Cost | Notes |
|---|---|---|
| LinkedIn (Showcase Page) | FREE | Needs OAuth app |
| Mastodon | FREE | Instant access token |
| Bluesky | FREE | App password only |
| Facebook Page | FREE | Graph API |
| Reddit (Optional) | FREE | Disabled unless an active official destination is explicitly configured |
| Threads | FREE | Meta Developers |

---

## 🚀 DEPLOYMENT — STEP BY STEP

### STEP 1: Add files to your GitHub repo

Option A: Add to existing `CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM` repo (recommended)
Option B: Create new repo: `CYBERDUDEBIVASH-SYNDICATION-ENGINE`

Copy the entire `syndicate/` folder into the root of your chosen repo.  
Your repo structure should look like:
```
your-repo/
├── syndicate/
│   ├── syndicate/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── rss_poller.py
│   │   ├── state_manager.py
│   │   ├── formatter.py
│   │   └── platforms/
│   │       ├── linkedin.py
│   │       ├── mastodon.py
│   │       ├── bluesky.py
│   │       ├── facebook.py
│   │       ├── reddit.py
│   │       └── threads.py
│   ├── data/
│   │   └── syndication_state.json
│   ├── requirements_syndicate.txt
│   └── .github/workflows/syndicate.yml
```

> ⚠️ Move `.github/workflows/syndicate.yml` to the ROOT `.github/workflows/` folder of your repo.

---

### STEP 2: Add GitHub Secrets

Go to: `GitHub Repo > Settings > Secrets and variables > Actions > New repository secret`

Add secrets for each platform you want to use. **Platforms with empty secrets are auto-skipped.**

---

### 🔑 PLATFORM CREDENTIAL SETUP

#### ✅ MASTODON (Easiest — 2 minutes)
1. Log in to `mastodon.social`
2. Go to `Preferences > Development > New Application`
3. Name: `CyberDudeBivash Syndication`, Scopes: `write:statuses`
4. Copy **Your access token**

**GitHub Secrets:**
```
MASTODON_ACCESS_TOKEN = <your token>
MASTODON_INSTANCE_URL = https://mastodon.social
```

---

#### ✅ BLUESKY (2 minutes)
1. Log in to `bsky.app`
2. Go to `Settings > Privacy and Security > App Passwords`
3. Click `Add App Password`, name it `syndication-bot`
4. Copy the generated password

**GitHub Secrets:**
```
BLUESKY_HANDLE       = cyberdudebivash.bsky.social
BLUESKY_APP_PASSWORD = <your app password>
```

---

#### ✅ LINKEDIN (15 minutes)
1. Go to `linkedin.com/developers > Create App`
2. App name: `CyberDudeBivash Syndication`
3. LinkedIn Page: Select your Company/Showcase page
4. In Products tab: Request `Marketing Developer Platform`
5. In Auth tab: Add OAuth 2.0 scope: `w_organization_social`, `r_organization_social`
6. Use OAuth flow to get access token (use https://www.linkedin.com/developers/tools/oauth/token-generator)

**Get your Organization URN:**
- Showcase page URL is: `linkedin.com/showcase/cyberdudebivash-sentinel-apex/`
- Go to: `https://api.linkedin.com/v2/organizationalEntityFollowerStatistics?q=organizationalEntity&organizationalEntity=urn:li:organization:XXXXXXX`
- Or check via Graph Explorer after auth

**GitHub Secrets:**
```
LINKEDIN_ACCESS_TOKEN = <access token>
LINKEDIN_AUTHOR_URN   = urn:li:organization:XXXXXXX   ← Showcase page ID
LINKEDIN_PERSONAL_URN = urn:li:person:XXXXXXX          ← Optional personal profile
```

---

#### ✅ FACEBOOK (15 minutes)
1. Go to `developers.facebook.com > My Apps > Create App`
2. Type: `Business`
3. Add product: `Facebook Login` + `Pages API`
4. Go to Graph API Explorer
5. Get User Access Token with: `pages_manage_posts`, `pages_read_engagement`
6. Exchange for Long-Lived Token (valid 60 days, renewable):
   ```
   GET https://graph.facebook.com/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={app-id}
     &client_secret={app-secret}
     &fb_exchange_token={short-lived-token}
   ```
7. Get your Page Access Token:
   ```
   GET https://graph.facebook.com/me/accounts?access_token={long-lived-token}
   ```
8. Find your Page ID and Page Access Token in the response

**GitHub Secrets:**
```
FACEBOOK_PAGE_ID           = <numeric page ID>
FACEBOOK_PAGE_ACCESS_TOKEN = <page access token>
```

---

#### ✅ REDDIT (10 minutes)
1. Go to `reddit.com/prefs/apps > Create another app`
2. Type: `script`
3. Name: `CyberDudeBivash Syndication`
4. Redirect URI: `https://cyberdudebivash.com`
5. Copy Client ID (under app name) and Client Secret

**GitHub Secrets:**
```
REDDIT_CLIENT_ID     = <client id>
REDDIT_CLIENT_SECRET = <client secret>
REDDIT_USERNAME      = <active official reddit username>
REDDIT_PASSWORD      = <your reddit password>
REDDIT_SUBREDDIT     = <approved subreddit or profile destination>
```

---

#### ✅ THREADS (20 minutes)
1. Go to `developers.facebook.com > Create App > Business`
2. Add `Threads API` product
3. Complete OAuth flow for `threads_basic` + `threads_content_publish` scopes
4. Exchange for long-lived token (valid 60 days)
5. Get your User ID: `GET https://graph.threads.net/v1.0/me?access_token={token}`

**GitHub Secrets:**
```
THREADS_ACCESS_TOKEN = <long-lived access token>
THREADS_USER_ID      = <numeric user ID>
```

---

### STEP 3: Move workflow file

```bash
mkdir -p .github/workflows
cp syndicate/.github/workflows/syndicate.yml .github/workflows/syndicate.yml
```

Or manually move `syndicate.yml` to root `.github/workflows/` in your repo.

---

### STEP 4: Commit and push

```bash
git add .
git commit -m "feat: Add Sentinel Syndication Engine v1.0 — RSS to Social Media"
git push
```

The workflow schedule must be explicitly enabled and validated before automated dispatch. Do not assume a successful post without a provider response.

---

### STEP 5: Manual test run

Go to: `GitHub Repo > Actions > CyberDudeBivash Sentinel Syndication Engine > Run workflow`

Check the logs to confirm each platform posts successfully.

---

## 📊 HOW IT WORKS

```
[cron: every 2h]
       │
       ▼
  GitHub Actions
       │
       ▼
  Fetch RSS Feed ──► Parse new items ──► Compare with state.json
       │
       ▼
  For each new post:
    ├── LinkedIn (Showcase Page)
    ├── Mastodon
    ├── Bluesky
    ├── Facebook Page
    ├── Reddit (only when explicitly configured)
    └── Threads
       │
       ▼
  Update state.json ──► Git commit ──► Push to repo
```

State is stored in `data/syndication_state.json` — committed back to repo after each run.  
If a platform fails, it's **not** marked as posted → will retry on next run.

---

## 🔄 CUSTOMIZATION

**Change run frequency** — Edit `cron:` in `syndicate.yml`:
- Every 1 hour: `0 * * * *`
- Every 30 min: `*/30 * * * *`
- 4x daily: `0 6,12,18,0 * * *`

**Change hashtags** — Edit `HASHTAGS_COMMON` and `HASHTAGS_EXTRA` in `config.py`

**Add second blog** — Duplicate job in workflow with different `RSS_URL` env var

**Platform post format** — Customize in `formatter.py` per platform

---

## 🛡️ SECURITY

- All credentials are GitHub Secrets — never in code
- State file contains only post metadata (no credentials)
- Each platform module fails gracefully — one failure doesn't break others
- Run logs archived as GitHub Actions artifacts (30 day retention)

---

*CYBERDUDEBIVASH PVT. LTD. | Bhubaneswar, Odisha, India | © 2026*  
*intel.cyberdudebivash.com | cyberdudebivash.com*
