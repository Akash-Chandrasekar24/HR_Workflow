# Automated Resume Screening & HR Decision Support Platform

Production-grade, enterprise recruitment screening system powered by FastAPI, Direct Google Drive file retrieval, LLM Structured Extraction (Gemini / OpenAI), Multi-Role HR Rule Engine, Interviewer Workload Balancing, and Automated Microsoft Teams & Calendar scheduling.

> 📖 **Comprehensive Technical Documentation**: For full architecture diagrams, module decompositions, fallback algorithms, API specifications, and scale design, refer to [**`TECHNICAL_DOCUMENTATION.md`**](file:///e:/New%20folder%20%282%29/GWC/HR_workflow/TECHNICAL_DOCUMENTATION.md).

---

## Key Highlights

- **Zero Google Service Account Setup**: Automatically retrieves resumes via Direct Base64 Webhook payloads or Direct HTTP Drive download links. No GCP Console Service Account configuration required.
- **LLM vs Rule Engine Isolation**: LLM is restricted to factual JSON extraction from resume text with a 100% deterministic local regex/AST fallback.
- **Multi-Role Support**: Pre-configured criteria for **AI / ML Engineer**, **Full Stack Developer**, **Data Analyst**, and **Python Developer** in `app/config/job_rules.json`.
- **Manual Interviewer Assignment & Live Capacity Tracker**: Domain-filtered assignment dropdowns and dynamic workload counters (`Total Load`, `Meetings Fixed`, `Yet To Be Fixed`).
- **Dynamic Excel Roster Upload**: Upload employee rosters (`.xlsx`) to populate and manage technical interviewers dynamically.
- **Automated 2-Minute Gmail IMAP Watcher**: Scans inbox replies, extracts natural language availability slots, and books Teams meetings with persistent deduplication.
- **AI Interviewer Copilot (Word .docx + Original Resume Attachment)**: Synthesizes 10 tailored technical questions and attaches both the `.docx` question sheet and the candidate's exact Google Drive resume to the interviewer's briefing email.


---

## Quick Start (Local Setup)

### 1. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Variables (.env)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Run FastAPI Application
```bash
python app/main.py
```
- **HR Dashboard UI**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **API OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Testing

Run the full automated test suite (24 unit & integration tests):
```bash
pytest tests/
```
