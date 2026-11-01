anora AI

Planora is a local-first event planning workspace. It turns event requirements into a persisted budget, planning timeline, ideas, guest records, and an event-day run sheet. The assistant uses real backend tools. Without a Gemini key, the local assistant can create events and handle clear budget, timeline, theme, guest, vendor, invitation, and schedule requests. Add a server-side Gemini key for open-ended ADK conversations.

The starter workspace is labeled **Demo workspace**. Its Jaipur wedding and costs are examples for exploring the dashboard; every price is a planning estimate, not a vendor quotation. The vendor list starts empty. Search and comparison only use records you enter.

## Run locally

Prerequisites: `uv`, Python 3.11–3.13, and Node.js 22.12 or later.

From this directory, install the backend dependencies:

```powershell
uv sync
Copy-Item .env.example .env
```

Start the API in one terminal:

```powershell
uv run uvicorn app.fast_api_app:app --reload --host 127.0.0.1 --port 8000 --env-file .env
```

Start the web app in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite forwards `/api` requests to the local FastAPI server. For a single-server preview, build the frontend with `npm run build`; FastAPI will serve `frontend/dist` on port 8000.

## Gemini-backed assistant (optional)

Set `GOOGLE_API_KEY` in `.env`. The key is read on the backend and is never sent to the browser. Restart the API after changing it. The ADK agent uses `MODEL_NAME`, which defaults to the model selected by the scaffold.

If you leave the key blank, Planora stays in local mode. Local mode still writes through the same SQLite tools, calculations, and event endpoints; it uses a focused request router instead of a generative model.

## Vercel prototype deployment

The Vercel build serves the frontend from `public/` and runs the FastAPI app as a Python Function. Without a configured Gemini key, the assistant uses local mode. Vercel's function filesystem is temporary, so this prototype stores SQLite data under `/tmp`; do not enter real guest, vendor, or event data. Changes can reset between visits or function instances. Add a managed persistent database before using the app for real planning.

## What works in the prototype

- Natural-language and form-based event creation, persistent event context, and targeted updates to budget estimates and deadlines.
- Category budget allocations, actual expenditure tracking, remaining-budget calculations, budget changes, and estimates clearly marked as estimates.
- Timeline milestones with completion tracking, overdue flags, and date-based rescheduling.
- Theme concepts, invitation drafting, event-day run sheets, alternatives, and event reports.
- Guest create, edit, RSVP tracking, CSV import, and CSV export.
- Vendor records entered by the user, filtering, and side-by-side comparison. No external vendor search is connected, and Planora does not invent vendors, ratings, contact details, or availability.
- Responsive React workspace with budget visualizations and an assistant panel.

## Local data and safety

Events, tasks, expenses, guests, vendors, and chat history are stored in `data/planora.db` by default. Set `PLANORA_DB_PATH` to move it. The app does not contact guests or vendors, book vendors, send invitations, or process payments. Invitation generation creates a draft only.

To reset the sample workspace, stop the API and remove `data/planora.db`; the next start recreates the labeled demo event. Keep `.env` and the database file private.
