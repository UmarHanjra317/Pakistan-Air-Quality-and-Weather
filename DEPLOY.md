# Deploying the live dashboard (GitHub + Render)

**Why two services?** GitHub stores your code (and gives you the repo link for your submission), but GitHub Pages
can only host static files - it cannot run a Flask/Python server. So: code on **GitHub**, running app on **Render**
(free tier), which pulls the code from GitHub automatically.

## 0. Run it on your own computer first (VS Code)
1. Install Python 3.10+ (tick **Add python.exe to PATH** on Windows) and VS Code with the **Python** extension.
2. VS Code -> **File -> Open Folder** -> choose the folder that contains `config.py` (`Pakistan-Air-Quality-and-Weather`).
3. Terminal -> New Terminal, then:
```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python backend/app.py
```
4. Open <http://127.0.0.1:5000>. The first start downloads live data (about a minute); after that it refreshes every 15 minutes by itself.
   Or press **F5** and pick *Run dashboard (Flask)* (Run and Debug panel).
5. If VS Code asks for an interpreter: Ctrl+Shift+P -> *Python: Select Interpreter* -> the one inside `venv`.

## 1. Create a GitHub account
1. Go to <https://github.com> -> **Sign up**.
2. Enter your email, a password and a username (it becomes part of your links, e.g. `github.com/yourname`).
3. Solve the puzzle, then enter the verification code GitHub emails you.
4. Choose the **Free** plan. Done.

## 2. Install Git (once)
Download from <https://git-scm.com/downloads>, install with the default options, then in a terminal:
```bash
git config --global user.name  "Your Name"
git config --global user.email "the-email-you-used-on-github@example.com"
```

## 3. Create the repository
1. On GitHub click **+** (top right) -> **New repository**.
2. Name: `Pakistan-Air-Quality-and-Weather`. Choose **Public**.
3. Leave "Add a README / .gitignore / license" **unticked** (the project already has them). Click **Create repository**.

## 4. Upload the project
Open a terminal **inside the project folder** (the one containing `config.py`) and run:
```bash
git init
git add .
git commit -m "Live air-quality dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/Pakistan-Air-Quality-and-Weather.git
git push -u origin main
```
The first push opens a browser window to sign in to GitHub. (No-terminal alternative: install *GitHub Desktop*,
"Add local repository", then **Publish repository**.)
Refresh the repo page - your files should be there, and `.gitignore` keeps the generated data out of the repo.

## 5. Put it online with Render (free)
1. Go to <https://render.com> -> **Get Started** -> **Sign in with GitHub** and authorise it.
2. **New +** -> **Blueprint** -> pick your `Pakistan-Air-Quality-and-Weather` repo -> **Apply**.
   (Render reads `render.yaml`, so build/start commands are already set.)
3. Wait 3-5 minutes for the first build. The first start also downloads the data from the API (about a minute).
4. Open the URL Render shows (like `https://pakistan-air-quality.onrender.com`). Check `/api/status` too.

From now on every `git push` redeploys automatically, and the app checks for fresh API data every 15 minutes.

**Free-tier behaviour:** Render puts a free service to sleep after 15 minutes without visitors; the next visit takes
about a minute to wake it, and the app re-downloads its data on wake-up (the disk is wiped on restart).

## 6. (Optional) Keep the data fresh even with no visitors
The workflow `.github/workflows/refresh.yml` calls `POST /api/refresh` every hour.
Enable it: repo -> **Settings** -> **Secrets and variables** -> **Actions** -> **Variables** -> **New repository variable**
-> Name `APP_URL`, Value = your Render URL (no trailing slash). Test it from the **Actions** tab -> *Refresh live data* -> **Run workflow**.

## 7. Opening everything on your phone
* Running dashboard: the Render link from step 5 (browser -> *Add to Home Screen*).
* Code: GitHub mobile app, or `github.dev` / Codespaces (see README section 9).
* Never upload the `venv/` folder - `.gitignore` already blocks it; it is the reason the original zip was 130 MB.

## Troubleshooting
| Problem | Fix |
|---|---|
| `git push` asks for a password and rejects it | GitHub no longer accepts passwords in the terminal: use the browser sign-in that Git opens, or GitHub Desktop. |
| Render build fails | Open the build log; it usually names a missing package - add it to `requirements.txt` and push. |
| Page shows "Could not reach the API" | The service is waking up - wait a minute and reload. |
| Header shows "Offline CSV data" (orange) | The Open-Meteo API was unreachable at start-up; the bundled CSV is being shown. It retries automatically within 5 minutes. |

### Automatic Data Refresh

The application automatically checks for updated weather and air-quality
data every 15 minutes using a background scheduler.

The scheduler runs independently of dashboard requests while the
Flask application is running.

Only one refresh operation can run at a time. If a refresh takes
longer than 15 minutes, the next refresh waits until the current
operation finishes.

Users can also manually refresh the data from the dashboard.