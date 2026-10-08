# GitHub Roast and Rescue

Enter a GitHub username and get an honest score, a short roast of the work, and a **Rescue** plan.
Every point links to the repository and names exactly what is missing. Nothing is guessed.

**Live link:** `<add your Cloud Run URL here after deploying>`

## The problem

Student GitHub profiles are often empty, messy, or full of half-finished projects, and nobody explains
what a good one looks like. "Build a portfolio" is common advice; "your `myapp` repo has no description,
a 19-character README and has not been pushed to in 400 days" is useful advice.

## Who it is for

Students and early-career developers who are about to share their GitHub with recruiters, plus the
mentors and teachers who review those profiles.

## Approach

1. **Read** the public GitHub REST API: profile, up to 100 repositories, the 6 most relevant ones in depth
   (README, file list, last 30 commits by the owner), the profile README repo, and recent push events.
   Pinned repositories need a token (GitHub only exposes them through GraphQL); without one the app uses
   the most recently pushed repositories and says so.
2. **Summarize** the language mix and stars across the repositories analysed in depth, with the scope shown
   in the report so partial samples are not mistaken for the whole profile.
3. **Review** per-repository health cards with findings, language, stars and last push date, plus a 7-day
   action plan based on the highest-priority fixes.
4. **Plan** which top fixes to tackle and preview a rough, clearly labeled estimate of the score impact;
   mark fixes complete to track local progress by username in the current browser.
5. **Keep or share** the result by copying a plain-text summary or printing the report / saving it as a PDF.
6. **Judge** with fixed rules (no AI involved), so the same profile always gets the same score.
7. **Explain**: a roast and a Rescue plan built from the findings: five ordered fixes, a rewritten profile
   README, better repository descriptions, and the two projects to finish first.
8. **Polish** (optional): **Google Gemini** rewrites the wording of the roast, README and descriptions.
   It receives only the facts the app collected, and its answer is discarded unless it keeps every project
   link, stays within length limits and only describes repositories that have README text to base it on.
   Without a key, or if Gemini fails, the template text is used.

### Score (100 points)

| Part               | Points | What is checked                                                                               |
| ------------------ | ------ | --------------------------------------------------------------------------------------------- |
| Profile            | 20     | bio (5), profile README (10), website/location/company (5)                                    |
| Repository quality | 50     | per repo: description, README exists, README explains how to run, license, tests, topics      |
| Activity           | 20     | latest push within 30/90/180 days (12), commits spread over several of the last 12 months (8) |
| Finishing          | 10     | repos not abandoned for a year (7), non-vague commit messages (3)                             |

A profile with fewer than two public, non-fork repositories is "nearly empty": it gets **no score** and a
**starter plan** instead. Private repositories cannot be seen through the public API, so a profile that
looks empty may simply be private.

## Setup

Requires Python 3.10 or newer.

### Windows (PowerShell)

```powershell
cd github-roast-and-rescue
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt

# Optional keys, set for this window only (never put them in the code):
$env:GITHUB_TOKEN = "your-github-token"
$env:GEMINI_API_KEY = "your-gemini-key"

flask --app app.main run --debug     # open http://127.0.0.1:5000
```

### Windows (Command Prompt)

```bat
cd github-roast-and-rescue
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
set GITHUB_TOKEN=your-github-token
set GEMINI_API_KEY=your-gemini-key
flask --app app.main run --debug
```

Run the tests the same way on Windows: `py -m unittest discover -s tests -t . -v`.
`gunicorn` in `requirements.txt` is only used inside the Docker image on Cloud Run; it installs on Windows
but you do not run it there, use the `flask` command above.

### macOS / Linux

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITHUB_TOKEN=your-github-token      # optional
export GEMINI_API_KEY=your-gemini-key      # optional
flask --app app.main run --debug           # http://127.0.0.1:5000
```

The keys are optional: without them the app still works (with the lower GitHub limit and template wording).

Secrets are read only from environment variables, and nothing is hard-coded. `.env.example` lists every variable; `.env` is git-ignored.

| Variable                                                  | Purpose                                                                                   |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `GITHUB_TOKEN`                                            | optional; raises the GitHub limit from 60 to 5,000 requests/hour and enables pinned repos |
| `GEMINI_API_KEY`                                          | optional; enables Gemini wording polish                                                   |
| `GEMINI_MODEL`                                            | defaults to `gemini-2.5-flash`; change it if Google retires that name                     |
| `CACHE_TTL_SECONDS`, `MAX_REPOS`, `RATE_LIMIT_PER_MINUTE` | tuning, safe defaults built in                                                            |

A profile costs roughly 3 requests per analysed repository plus about 5 more (about 23 with the default of
6). Anonymous use therefore allows only a couple of fresh profiles per hour, so set `GITHUB_TOKEN` for real
use. Every GitHub response and every finished report is cached (default one hour), so repeat lookups are free.

## Run the tests

```bash
python -m unittest discover -s tests -t . -v      # Windows: py -m unittest discover -s tests -t . -v
```

No extra packages and no network are needed. (`pytest` also works if you have it installed.)
The tests cover validation, caching, the GitHub client (with fake responses), scoring, evidence on every
finding, the Rescue plan, Gemini grounding and fallback, and the web routes.

## Demo usernames

These three work **offline**, with built-in sample data (clearly labelled in the UI):

| Username        | Shows                                                               |
| --------------- | ------------------------------------------------------------------- |
| `sample_strong` | a tidy profile that scores 100                                      |
| `sample_messy`  | no descriptions, stub READMEs, abandoned and empty repos; scores 13 |
| `sample_empty`  | no repositories of its own, so the starter plan                     |

To find real accounts for a live demo, run `python scripts/check_demo_users.py name1 name2 name3`
from a machine that can reach GitHub. It prints which are strong, messy or nearly empty. Only demo with
accounts whose owners are happy to be shown (your own, or a friend's).

## Deploy to Google Cloud Run

```bash
gcloud run deploy github-roast --source . --region asia-south1 --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,GITHUB_TOKEN=github-token:latest
```

Create the two secrets first in Secret Manager (`gcloud secrets create ...`). Cloud Run builds the
`Dockerfile`, sets `PORT`, and the app listens on it. Paste the service URL in the **Live link** line above.

## Accessibility and safety

Labelled form field, error messages announced with `role="alert"`, status updates in `aria-live` regions,
skip link, visible focus outlines, keyboard-operable copy button, semantic headings, `meter` elements with
text labels, alt text on the avatar, AA-contrast colours, reduced-motion support. Inputs are validated on
the client and the server; all rendered text uses `textContent`; a strict Content-Security-Policy is set;
`/api/analyze` is rate-limited per visitor.

## Layout

```
app/        config, cache, validation, github_client, analyzer, rescue, roast, gemini, report, service, main
app/templates, app/static   the web page
tests/      unittest suite
scripts/    check_demo_users.py
Dockerfile  requirements.txt  .env.example
```
