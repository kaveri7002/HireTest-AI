# HireTest AI

HireTest AI is an AI-assisted software testing platform. Its application under test is HireTest Jobs, a job portal. The project is being implemented in phases; this first working foundation includes the React/TypeScript command center, an API-backed jobs view, accounts, MongoDB persistence, and a safe rule-based test-case generator.

> This is a new project beside TaskFlow QA. The dashboard never fabricates test outcomes: metrics are read from persisted test-result records and remain empty until tests have actually run.

## Current phase

### Implemented and verified

- React + Vite + TypeScript frontend with a responsive testing command center.
- Flask REST API with MongoDB Atlas/PyMongo configuration.
- Student and recruiter account registration/sign-in with hashed passwords and signed expiring tokens.
- MongoDB-backed job listing, recruiter job creation, student applications, and recruiter applicant status updates.
- Recruiters can view applications only for jobs they posted; the job board identifies other recruiters' listings so their applicant controls are not shown.
- Student job-match profiles and deterministic recommendations based on skills and interests; fictional demo listings are excluded.
- Validated application contact details, skills, cover notes, and optional HTTPS resume links, visible to the posting recruiter.
- Persisted application-status and interview notifications, delivered in-app over authenticated Socket.IO connections and available in the notification inbox.
- Recruiter interview scheduling with future-date validation and optional HTTPS meeting links; students see the invitation in their application list and inbox.
- Job-type filters, job sorting, device-local saved-job shortlists, and recruiter applicant search/status filters.
- Rule-based test-case generation stored per signed-in tester; test cases can be edited and approved before execution, and no generated code is executed.
- Clearly labeled fictional job listings and unapproved starter test-case examples appear when a workspace is empty. Demo listings cannot accept applications, and examples do not create test results.
- The installable app checks for updates on launch, when returning to the app, and periodically while online.
- Dashboard counts sourced from stored test-result records.
- API tests and a Playwright page-object end-to-end job-application test.

### Not implemented yet

The full master prompt is larger than a single safe delivery. Background Playwright test execution, bug triage, visual regression, PDF reports, and AI-provider integration are later phases. The UI labels these areas as under development instead of presenting fake outcomes.

Job recommendations currently use keyword matching against published job titles, descriptions, and locations; they are deterministic, not AI-generated. Notifications are persisted and delivered in the app while a user is connected. Email and operating-system push notifications require an external provider and are not configured.

## Architecture

```text
HireTest-AI/
├── frontend/       React + TypeScript + Vite + Tailwind + Recharts
├── backend/        Flask REST API + Socket.IO + PyMongo
├── backend/tests/  API tests
├── docker/         Container and local stack configuration (next phase)
└── README.md
```

## Requirements

- Node.js 18+ and npm (the project was verified with Node.js 20.18).
- Python 3.10+.
- MongoDB local or a MongoDB Atlas connection string.
- Playwright Chromium for browser automation.

## Local setup

From the HireTest-AI folder:

1. Configure the API:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   Copy-Item .env.example .env
   ```

   Set `MONGODB_URI` in `.env` to your own local MongoDB or Atlas URI and replace `SECRET_KEY` with a long random value. Never commit `.env` or paste database credentials into chat.

2. Configure and run the frontend:

   ```powershell
   cd frontend
   npm install
   Copy-Item .env.example .env
   npm run dev
   ```

3. In a separate PowerShell window, run the API from the project root:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m backend.app
   ```

   Open the Vite URL (usually `http://localhost:5173`). Create a tester or recruiter account. The frontend proxies API calls to `http://127.0.0.1:5000` during development.

   Recruiters can post jobs and review applicants from **HireTest Jobs**. Register a second account as a student/tester to browse and apply; submitted applications and status updates are shown in each account's job portal view.

## Run tests

```powershell
.\.venv\Scripts\Activate.ps1
Push-Location frontend
npm ci
npm run build
Pop-Location
python -m playwright install chromium
python -m pytest backend\tests
```

The Playwright end-to-end test exercises the actual job portal and records no synthetic test outcomes in the dashboard. The independent background test-execution worker is not implemented yet.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Persistent secret for signed login tokens; use a random value outside local development. |
| `MONGODB_URI` | MongoDB connection URI. |
| `MONGODB_DATABASE` | Database name; defaults to `hiretest_ai`. |
| `FRONTEND_ORIGINS` | Comma-separated frontend origins allowed by CORS. |
| `TOKEN_MAX_AGE_SECONDS` | Login token lifetime. |
| `VITE_API_URL` | Optional API origin; leave empty for local Vite proxy. |
| `AI_API_KEY` | Optional future AI integration. Keep blank until a provider is configured. |

## GitHub and deployment

This project is published at [github.com/kaveri7002/HireTest-AI](https://github.com/kaveri7002/HireTest-AI). It includes a Render Blueprint (`render.yaml`) and a multi-stage Dockerfile for deploying the frontend and API as one web service.

To deploy, create a new Blueprint from this repository in Render and apply the `hiretest-ai` service. During setup, enter `MONGODB_URI` in Render's private environment-variable prompt using your own MongoDB Atlas connection string; do not put credentials in the repository or chat. Render generates `SECRET_KEY` automatically. The site can load without a database URI, but account and data APIs will return a configuration error until MongoDB is configured. Configure Atlas Network Access to allow the Render service to connect. The free Render service may sleep when idle. Configure staging separately before using defect injection; there is no production defect injection in the current phase.
