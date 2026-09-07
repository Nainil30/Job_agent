 # 🛰️ Autonomous NPI & Hardware TPM Job Intelligence Agent

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI: Daily Job Scout](https://img.shields.io/badge/GitHub_Actions-Scheduled_Cron-purple.svg)](https://github.com/)
[![LLM: Gemini 2.0 Flash](https://img.shields.io/badge/LLM-Gemini_2.0_Flash-orange.svg)](https://ai.google.dev/)
[![Protocol: FastMCP](https://img.shields.io/badge/Protocol-Model_Context_Protocol_(MCP)-teal.svg)](https://github.com/jlowin/fastmcp)
[![Cost: $0.00/mo](https://img.shields.io/badge/Operating_Cost-$0.00%2Fmo-brightgreen.svg)]()

An autonomous, zero-cost, enterprise-grade job intelligence agent designed to scout, evaluate, and track high-fit opportunities across Tier-1 hardware and datacenter infrastructure companies (Nvidia, Amazon AWS, Apple, Google, and semiconductor leaders). 

The system leverages direct ATS REST ingestion, a two-pass deterministic and LLM-as-a-Judge evaluation engine, an append-only Git-tracked NDJSON ledger, and an interactive **Model Context Protocol (MCP)** server for local AI IDEs.

---

## 🎯 The Problem

Hunting for specialized, high-demand hardware roles (e.g., **New Product Introduction (NPI) Operations**, **Materials Program Management (MPM)**, and **Datacenter Hardware TPM**) across fragmented enterprise career portals presents several engineering challenges:

1. **Brittle Browser Automation:** Career sites rely on dynamic Single Page Applications (SPAs). Standard Selenium/Playwright scrapers break when DOM class names shift and add unnecessary compute overhead.
2. **Aggregator Latency:** Traditional job scrapers (LinkedIn, Indeed, Google Jobs) exhibit 24–72 hour indexing delays, causing candidates to miss early application windows.
3. **Token Inefficiency & Cost:** Feeding raw, unparsed job descriptions (JDs) directly into LLMs for dozens of roles daily quickly exhausts API rate limits and token budgets.
4. **Keyword Noise & Misalignment:** Naive keyword searches flood inboxes with over-senior roles (Directors, VPs) or non-target domains (sales, software frontend, legal).

---

## 💡 Key Architectural Highlights

* **Direct ATS API Ingestion:** Targets keyless internal JSON endpoints (Workday CXS, Amazon Jobs API) directly via `httpx`. Eliminates browser emulation for a sub-30-second daily execution.
* **Two-Pass Hierarchical Filtering:**
  * **Pass 1 (Deterministic):** Evaluates titles and locations using pre-compiled regex allowlists and blocklists at **zero token cost**, shedding ~80% of irrelevant volume.
  * **Pass 2 (LLM-as-a-Judge):** Uses **Gemini 2.0 Flash** with strict **Pydantic schema validation** to output 0–100 fit scores, gap analyses, and tailored resume bullet points.
* **Append-Only Canonical Ledger (`data/jobs_ledger.ndjson`):** Replaces opaque binary SQLite commits with Git-friendly, newline-delimited JSON. Diff-friendly, human-readable, and zero-bloat.
* **Ephemeral In-Memory SQL Layer:** Automatically mounts the NDJSON ledger into an in-memory SQLite table (`:memory:`) at runtime for instant relational queries.
* **Interactive MCP Interface:** Exposes the historical database and evaluation engine to **Cursor** and **Claude Desktop** via FastMCP.
* **$0.00 / Month Infrastructure:** Fully automated via GitHub Actions scheduled cron runs within free API and CI/CD quotas.
 
 
## 📡 Ingestion Protocol Matrix

Target enterprise career platforms fall into three architectural categories:

| Target Company | Platform Architecture | Ingestion Method | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Nvidia** | Workday CXS | `POST /wday/cxs/.../jobs` | **Verified** | Structured JSON payload; parses title, location, bullets, and job path. |
| **Amazon** | Amazon Jobs REST | `GET /en/search.json` | **Verified** | Direct public query; strictly filtered by `city=Austin` and AWS Infra keywords. |
| **AMD / Qualcomm / AMAT** | Workday CXS / Enterprise | `POST /wday/cxs/.../jobs` | **Active** | Standardized Workday client parsing multi-location requisitions. |
| **Apple** | Apple Careers API | `POST /api/v1/job/search` | **Active** | Custom REST client handling session headers. |
| **Google** | Google Careers API | `GET /api/v3/search/` | **Active** | Direct endpoint client extracting hardware and supply chain org paths. |
| **Tesla** | Dynamic SPA | Headless Browser Fallback | **Isolated** | Handled via decoupled weekly scraper to prevent dynamic DOM shifts from breaking API pipelines. |


## ⚙️ Core Engineering Decisions

### 1. Two-Pass Evaluation (Token & Cost Optimization)
Directly piping every scrape result into an LLM wastes API quotas on irrelevant listings (e.g., barista positions, software internships, VP roles).

* **Pass 1 (Deterministic):** An instantaneous regex engine checks job titles against:
  * **Blocklist:** Discards `intern`, `co-op`, `director`, `vp`, `sales`, `legal`, `recruiter`, `technician`.
  * **Allowlist:** Requires matches on `npi`, `materials`, `supply chain`, `hardware tpm`, `datacenter`, `operations program`.
  * **Location Gate:** Enforces geographic constraints (e.g., strictly `Austin, TX` for Amazon roles).
* **Pass 2 (LLM-as-a-Judge):** Surviving listings are sent to **Gemini 2.0 Flash** (`temperature=0.1`) with a strict Pydantic JSON schema. The model calculates a 0–100 score, filters out positions demanding >6 years of experience, identifies specific technical tooling gaps, and drafts 3 tailored resume bullet points.

### 2. Git-Friendly Canonical Storage (NDJSON vs. SQLite)
Committing binary files (`jobs.db`) to Git leads to rapid repository bloat and opaque commit diffs.

* **Append-Only NDJSON (`data/jobs_ledger.ndjson`):** Each job record is stored as a single-line JSON string. Git tracks additions as clean, human-readable line insertions.
* **Ephemeral In-Memory SQL:** When interactive querying is required, `src/storage/db.py` mounts the NDJSON ledger into an in-memory SQLite instance (`:memory:`) in milliseconds, giving the FastMCP server full relational SQL capabilities.

### 3. Interactive FastMCP Integration
Rather than confining results to a static file, the agent acts as an MCP server. Within **Cursor** or **Claude Desktop**, you can query your database conversationally:
> *"Show me all Nvidia and Amazon hardware roles scored above 85 this week, and draft 3 tailored bullet points for my resume matching Job ID JR2011480."*

## 📂 Repository Layout

npi-hardware-job-agent/
├── .github/
│   └── workflows/
│       └── daily_api_scout.yml      # CI/CD pipeline: daily scheduled cron & auto-committer
├── config/
│   ├── companies.yaml             # Target company ATS endpoints, tenants, and queries
│   └── persona.yaml               # Candidate profile, target roles, and location rules
├── data/
│   ├── jobs_ledger.ndjson         # Canonical append-only NDJSON database
│   └── readable_jobs.txt          # Formatted, human-readable ledger export
├── digests/
│   └── 2026-W35.md                # Weekly Markdown summaries with direct apply links
├── src/
│   ├── adapters/                  # Modular ATS network clients
│   │   ├── base.py                # Abstract Base Adapter class
│   │   ├── workday.py             # Universal Workday CXS client
│   │   ├── amazon.py              # Amazon Jobs REST API client
│   │   ├── google.py              # Google Careers API client
│   │   ├── apple.py               # Apple Jobs API client
│   │   └── browser_fallback.py    # Headless browser fallback scraper
│   ├── engine/                    # Filtering & Evaluation Core
│   │   ├── models.py              # Pydantic schema contracts (RawJobPosting, JobEvaluation)
│   │   ├── filter.py              # Pass 1 deterministic regex & location engine
│   │   └── evaluator.py           # Pass 2 LLM-as-a-Judge with Gemini 2.0 Flash
│   ├── storage/                   # Ledger, In-Memory DB, & Digest Generators
│   │   ├── ledger.py              # NDJSON reader/writer with SHA-256 deduplication
│   │   ├── db.py                  # In-memory SQLite relational indexer
│   │   └── reporter.py            # Weekly Markdown digest generator
│   ├── mcp/
│   │   └── server.py              # FastMCP interactive tools for Cursor / Claude Desktop
│   └── main.py                    # Unified CLI orchestrator
├── tests/
│   ├── test_filter.py             # Unit tests for deterministic rules & location gates
│   └── test_adapters.py           # Mock payload integration tests (via Respx)
├── view_jobs.py                   # Local CLI utility to inspect and export job ledgers
├── requirements.txt               # Production dependencies
├── .env.example                   # Environment variable template
└── README.md                      # System documentation

Part 5: Installation, Configuration, & Local Usage
Markdown
## 🚀 Quickstart & Local Setup

### 1. Prerequisites
* Python 3.11+
* Git
* A free Google AI Studio API Key ([Get one here](https://aistudio.google.com/))

### 2. Installation
Clone the repository and set up your virtual environment:

```bash
# Clone the repository
git clone [https://github.com/](https://github.com/)<YOUR_USERNAME>/npi-hardware-job-agent.git
cd npi-hardware-job-agent

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
3. Environment Configuration
Copy .env.example to .env and insert your Gemini API Key:

Bash
cp .env.example .env
Inside .env:

Code snippet
GEMINI_API_KEY=AIzaSyYourActualKeyHere
4. Run Unit Tests
Verify that deterministic filters, blocklists, and mock parsers pass:

Bash
pytest
5. Execute the Ingestion & Evaluation Pipeline
Run the daily scouting pipeline locally:

Bash
python src/main.py --mode api
6. Inspect Results
Formatted Markdown Preview: Open digests/2026-W35.md in VS Code and press Ctrl + K, V to view the styled summary table.

 python src/main.py --mode api
 Clear-Content data/jobs_ledger.ndjson

  python -m venv .venv  
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1

Readable Text Export: Run python view_jobs.py to print and export all evaluated jobs to data/readable_jobs.txt.


---

### Part 6: MCP Server & GitHub Actions Automation

```markdown
## 🤖 FastMCP Server Setup (Cursor / Claude Desktop)

Connect the agent's database and evaluation tools directly to your AI IDE:

```bash
# Start the FastMCP server locally
python src/mcp/server.py
Configuring Claude Desktop / Cursor
Add the server definition to your claude_desktop_config.json or Cursor MCP settings:

JSON
{
  "mcpServers": {
    "job-scout": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/npi-hardware-job-agent",
      "env": {
        "GEMINI_API_KEY": "AIzaSy..."
      }
    }
  }
}
Available MCP Tools:
get_weekend_review(min_score=80, company="Nvidia"): Returns high-fit job opportunities ranked by fit score.

evaluate_custom_jd(company, title, location, description): Evaluates any ad-hoc job description against your candidate persona.

generate_tailored_bullets(company, title, job_id): Retrieves a stored role and drafts 3 tailored resume bullet points matching the specific JD gaps.

⏰ CI/CD Cloud Automation (GitHub Actions)
The pipeline is automated to run every morning at 06:00 UTC via .github/workflows/daily_api_scout.yml:

YAML
name: Daily Autonomous Job Hunter

on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scout-jobs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: pytest
      - name: Ingest & Evaluate
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python src/main.py --mode api
      - name: Auto-Commit Changes
        run: |
          git config --global user.name "JobScout Bot"
          git config --global user.email "bot@users.noreply.github.com"
          git add data/ digests/
          git diff --staged --quiet || (git commit -m "chore(digest): daily job scan [skip ci]" && git push)
Enabling in Your Repository:
Push your code to GitHub:

Bash
git add .
git commit -m "feat: complete job scout engine"
git push origin main


