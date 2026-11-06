# NordicTidy social

Automatic posting of NordicTidy pins to Pinterest and posts to Instagram.

- `queue/*.json`: what gets posted, and when (Copenhagen time). Claude fills it up every month.
- `media/`: the images. Instagram reads them from this public repo.
- `links.json`: the Etsy link for each product. Update it when new listings go live.
- `poster/post.py`: the robot. GitHub Actions runs it every hour (`.github/workflows/post.yml`).
- `log/posted.json`: everything that has been posted, so nothing is posted twice.

Missed days are skipped, not posted late, so starting late never floods the accounts.

## Secrets (Settings → Secrets and variables → Actions)

| Name | Where it comes from |
| --- | --- |
| `PINTEREST_APP_ID` | developers.pinterest.com → your app |
| `PINTEREST_APP_SECRET` | same place |
| `PINTEREST_REFRESH_TOKEN` | run `python3 tools/pinterest_login.py` on your Mac |
| `IG_USER_ID` | Meta app → API setup with Instagram login |
| `IG_TOKEN` | same place → Generate token |
| `GH_PAT` | GitHub fine-grained token for this repo with **Secrets: Read and write**; lets the weekly workflow renew `IG_TOKEN` |

A platform without its secrets is skipped, so you can set up one at a time.

## Test

Actions → "Post to Pinterest and Instagram" → Run workflow. With "dry run" ticked it only prints what is due right now.
