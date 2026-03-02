# Drive_RAG_Indexing

Lupus – Investia RAG: chat UI over your Drive documents (embed + Supabase + Gemini).

## Deploy frontend on Vercel

1. **Push the repo to GitHub** (if not already).

2. **Go to [vercel.com](https://vercel.com)** → Sign in → **Add New** → **Project**.

3. **Import** your GitHub repo. Vercel will detect the config from `vercel.json` (builds the `frontend` app, outputs `frontend/dist`).

4. **Environment variable (optional):**  
   If your **backend** is deployed elsewhere (see below), add:
   - **Name:** `VITE_API_URL`  
   - **Value:** your backend API URL, e.g. `https://your-backend.railway.app/api/chat`  
   So the production frontend calls that URL instead of a relative `/api/chat`.

5. **Deploy** – Vercel will build and host the frontend. You’ll get a URL like `https://your-project.vercel.app`.

### Backend (API)

Vercel is serving only the **React frontend**. The **Python/Flask backend** (`api/server.py`) must run somewhere else that supports Python, for example:

- **[Railway](https://railway.app)** – connect the same repo, set root to project root, run `pip install -r requirements.txt && python -m api.server`, expose port 5000.
- **[Render](https://render.com)** – Web Service, build: `pip install -r requirements.txt`, start: `python -m api.server`, add env vars from `.env`.

Then set **`VITE_API_URL`** in Vercel to that backend URL (e.g. `https://your-app.railway.app/api/chat`), so the deployed frontend talks to your API.

## Run locally

- **Backend:** `pip install -r requirements.txt && python -m api.server` (from project root).
- **Frontend:** `cd frontend && npm install && npm run dev`.  
Open the frontend URL (e.g. http://localhost:5173); it calls the backend at http://127.0.0.1:5000 in dev.