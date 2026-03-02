# Drive_RAG_Indexing

Lupus – Investia RAG: chat UI over your Drive documents (embed + Supabase + Gemini).

## Deploy on Vercel (frontend + API in one project)

The repo is set up so **Vercel runs both the React app and the chat API** as serverless. No separate backend host.

1. **Push the repo to GitHub** (if not already).

2. **Go to [vercel.com](https://vercel.com)** → Sign in → **Add New** → **Project** → import your repo.

3. **Environment variables** (required for the API):  
   In the Vercel project → **Settings** → **Environment Variables**, add the same vars you use locally (from `.env`):
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SERVICE_RAG`
   - `GEMINI_API_KEY`
   - (optional) `GEMINI_API_KEY_2`  
   Use the same values as in your local `.env`. Do **not** commit `.env`; set them only in Vercel.

4. **Deploy** – Vercel will:
   - Build the frontend from `frontend/` and serve it at the project URL.
   - Deploy `api/chat.py` as a serverless function at **`/api/chat`** (POST for chat, OPTIONS for CORS).

5. The frontend in production calls **`/api/chat`** on the same domain, so you do **not** need to set `VITE_API_URL` unless you point the app at a different backend.

### If something doesn’t work

- Check **Vercel → Project → Settings → Environment Variables** and confirm all required vars are set for **Production** (and Preview if you use it).
- Check **Vercel → Deployments → [latest] → Functions** to see if `/api/chat` is listed and if it errors.
- In the browser, open DevTools → Network, send a message, and see whether the request to `/api/chat` returns 200 or an error (e.g. 500 and the response body).

## Run locally

- **Backend:** `pip install -r requirements.txt && python -m api.server` (from project root).
- **Frontend:** `cd frontend && npm install && npm run dev`.  
  Open the frontend URL (e.g. http://localhost:5173); it calls the backend at http://127.0.0.1:5000 in dev.
