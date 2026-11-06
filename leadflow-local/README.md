# LeadFlow — AI-Powered Lead Enrichment Engine

LeadFlow is an AI-powered lead enrichment and prospecting platform that transforms a list of companies into actionable sales leads.
Upload a CSV containing company information, and LeadFlow automatically researches their public websites, extracts useful business information and contact details, generates personalized outreach email drafts using an LLM, and assigns each prospect a potential lead score.
The goal is to reduce manual prospect research and help sales teams and freelancers identify and prioritize promising business opportunities.

##  Key Features

- **CSV Lead Import** — Upload CSV files containing company information to start the enrichment process.
- **Automated Website Research** — Visits publicly accessible company websites and gathers relevant business information.
- **Contact Discovery** — Extracts publicly available contact information and relevant business details.
- **AI-Powered Enrichment** — Uses Groq-powered LLM analysis to organize and interpret collected company information.
- **Personalized Outreach Drafts** — Generates contextual outreach email drafts based on the information discovered about each company.
- **Lead Scoring** — Evaluates enriched company profiles and assigns potential lead scores to help prioritize prospects.
- **Lead Management Dashboard** — View, review, and manage enriched leads through a centralized dashboard.

##  How It Works

1. **Import:** Upload a CSV containing company details.
2. **Research:** LeadFlow visits the companies' public websites using browser automation.
3. **Extract:** Relevant business information and publicly available contact details are collected.
4. **Enrich:** The collected information is analyzed and structured using an LLM.
5. **Score:** Each company receives a potential lead score based on its available information.
6. **Generate:** Personalized outreach email drafts are created for potential prospects.
7. **Review:** Explore enriched leads, scores, company information, and email drafts in the dashboard.

##  Technology Stack

| Component | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Frontend | React (prebuilt static bundle) |
| Database | SQLite |
| Browser Automation | Playwright |
| AI / LLM | Groq API |
| Server | Uvicorn |

##  Project Structure

The local bundle includes the Python API source, a prebuilt frontend bundle, and locked Python dependencies.

- `app/` — Backend application and API logic.
- `requirements.txt` — Locked Python dependencies.
- `leadflow.db` — Local SQLite database, automatically created on first run.
- Frontend bundle — Compiled dashboard served by the backend.

> **Note:** The original React source workspace is not included in this bundle. The dashboard can be used locally, but modifying its UI requires the original frontend source project.

##  Requirements

- Python 3.13
- Internet connection
- Groq API key (required for AI enrichment and LLM-powered analysis)

Internet access is also required for installing dependencies, downloading Playwright Chromium, and researching publicly accessible company websites.

##  Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/alpha900x/LeadFlow/
cd LeadFlow
```

### 2. Create a Virtual Environment

**Windows (PowerShell):**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Install Playwright Chromium

```bash
python -m playwright install chromium
```

On Debian/Ubuntu, if Chromium reports missing system libraries, run:

```bash
python -m playwright install --with-deps chromium
```

### 5. Configure the Groq API Key

LeadFlow uses Groq for AI-powered analysis and outreach generation.

The API key is not included in this repository. Set it as an environment variable in the terminal used to start the application.

**Windows (PowerShell):**

```powershell
$env:GROQ_API_KEY = Read-Host "Groq API key"
```

**macOS / Linux:**

```bash
read -s -p "Groq API key: " GROQ_API_KEY
printf '\n'
export GROQ_API_KEY
```

The default model is:

```text
openai/gpt-oss-120b
```

You can override the model using the `GROQ_MODEL` environment variable.

Optional request and token budget configurations:

```text
GROQ_SAFE_RPM
GROQ_SAFE_RPD
GROQ_SAFE_TPM
GROQ_SAFE_TPD
```

These variables allow you to configure safe request and token usage limits.

### 6. Run the Application

With the virtual environment activated and your API key configured, run:

```bash
python -m uvicorn app.local_app:app --host 127.0.0.1 --port 8000
```

Open the following URL in your browser:

**http://127.0.0.1:8000**

The dashboard and API will run locally on your machine.

Press `Ctrl + C` in the terminal to stop the server.

## ⚠️ Configuration & Limitations

- The first application run automatically creates a local SQLite database (`leadflow.db`).
- No preconfigured company database or sample leads are included.
- No Groq API key is bundled with the project.
- Without a Groq API key, the dashboard can still open, but AI-powered enrichment and analysis will be unavailable.
- Website research requires an active internet connection.
- The frontend is distributed as a compiled static bundle; its original React source is maintained separately.

## 🔒 Security & Responsible Usage

- Keep your Groq API key private. Never commit API keys or credentials to GitHub.
- Only research publicly accessible company websites.
- Respect website terms of service, robots.txt directives, and applicable rate limits.
- Treat discovered contact information as unverified until reviewed.
- Review AI-generated outreach drafts before sending them.

## 📄 License

Add your preferred license before distributing or reusing this project.