# LeadFlow — local build

This bundle runs the LeadFlow dashboard and API on your computer without
Replit's artifact router, API gateway, or deployment configuration. The
dashboard is included as a prebuilt static bundle; editing the React UI still
requires the original source workspace.

## What is and is not included

- The compiled dashboard and Python API source are included.
- No Replit configuration, API key, or company database is included.
- The first run creates `leadflow.db` in this folder.
- Groq analysis and live public-website research still require internet access.
  Without a Groq key, the dashboard opens but AI enrichment is unavailable.

## Requirements

- Python 3.13
- Internet access for installing packages, downloading Playwright Chromium,
  Groq analysis, and live website research

## Install

Create and activate a virtual environment, then install the included locked
dependencies:

### macOS / Linux

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Debian/Ubuntu Linux, if Chromium reports missing system libraries, install
them with `python -m playwright install --with-deps chromium`.

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Configure the Groq key

The key is not in this bundle. Set `GROQ_API_KEY` in the environment of the
terminal that starts the API. Do not put it in source files or commit it.

macOS / Linux (the input is hidden):

```sh
read -s -p "Groq API key: " GROQ_API_KEY
printf '\n'
export GROQ_API_KEY
```

Windows PowerShell:

```powershell
$env:GROQ_API_KEY = Read-Host "Groq API key"
```

`GROQ_MODEL` defaults to `openai/gpt-oss-120b`. The safe Groq request/token
budgets can be overridden with `GROQ_SAFE_RPM`, `GROQ_SAFE_RPD`,
`GROQ_SAFE_TPM`, and `GROQ_SAFE_TPD`.

## Run

With the virtual environment active and the key set, run:

```sh
python -m uvicorn app.local_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Stop the server with Ctrl+C.

## Existing company data

The Replit workspace keeps its SQLite database at
`artifacts/leadflow/backend/leadflow.db`. It is deliberately not in this bundle.
To bring those companies and results over, copy that file into this folder as
`leadflow.db` before the first local run. Keep a backup and do not upload it to
public source control.
