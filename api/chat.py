import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

log = logging.getLogger(__name__)

# RAG Chat API Endpoint
# This endpoint performs retrieval-augmented generation (RAG) chat:
# 1) Embed the user question
# 2) Retrieve relevant document chunks from Supabase vector DB
# 3) Construct a prompt with retrieved context
# 4) Generate an answer using Gemini language model
#
# Gemini API calls per user message:
# - strict/hybrid: 2 calls (1 embedContent for the question, 1 generateContent for the reply)
# - general: 1 call (generateContent only)
#
# Supported modes:
# - "strict": answer only from retrieved context
# - "hybrid": answer from context or general knowledge
# - "general": no context, answer from general knowledge
#
# Key environment variables:
# - SUPABASE_URL: URL of Supabase instance
# - SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_RAG: Supabase key (service role preferred for RLS bypass)
# - GEMINI_API_KEY: primary Gemini API key
# - GEMINI_API_KEY_2: optional secondary Gemini API key for fallback

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().strip("'\"").rstrip("/")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is required")

_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_RAG")
if not _SUPABASE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_RAG is required")
SUPABASE_SERVICE_ROLE_KEY = _SUPABASE_KEY.strip().strip("'\"")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")  # optional, not required server-side

_GEMINI = (os.environ.get("GEMINI_API_KEY") or "").strip().strip("'\"")
if not _GEMINI:
    raise ValueError("GEMINI_API_KEY is required")
GEMINI_API_KEY_1 = _GEMINI
GEMINI_API_KEY_2 = (os.environ.get("GEMINI_API_KEY_2") or "").strip().strip("'\"") or None  # optional fallback key

# Gemini models: embed is current; for chat default gemini-2.5-flash-lite (override with CHAT_MODEL in .env).
# One user message = 2 API calls: embedContent (question) + generateContent (reply).
EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gemini-2.5-flash-lite")

# Tunables
EMBED_DIM = int(os.environ.get("EMBED_DIM", "768"))
MATCH_COUNT = int(os.environ.get("MATCH_COUNT", "5"))
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.6"))
MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", "12000"))


# Helper to call Gemini REST API with key fallback
def _gemini_post(model: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calls the Gemini REST endpoint with key fallback.
    Tries key #1 first; on quota/429/5xx or transient errors, retries once with key #2 (if provided).
    """
    keys = [GEMINI_API_KEY_1]
    if GEMINI_API_KEY_2:
        keys.append(GEMINI_API_KEY_2)

    last_exc: Optional[Exception] = None
    last_text: Optional[str] = None

    for i, key in enumerate(keys, 1):
        key_label = f"key{i}"
        log.info("Gemini %s %s with %s", model, method, key_label)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}?key={key}"
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                log.info("Gemini %s %s with %s ok", model, method, key_label)
                return res.json()

            last_text = res.text
            log.warning("Gemini %s %s with %s status=%s %s", model, method, key_label, res.status_code, last_text[:200] if last_text else "")
            # Retry on rate-limit / quota / transient server errors
            if res.status_code in (429, 500, 502, 503, 504):
                if i < len(keys):
                    log.info("Retrying with next key")
                continue

            # Non-retryable error
            res.raise_for_status()
        except Exception as e:
            last_exc = e
            log.warning("Gemini %s %s with %s exception: %s", model, method, key_label, e)
            if i < len(keys):
                log.info("Retrying with next key")
            continue

    if last_exc:
        raise last_exc
    raise RuntimeError(f"Gemini call failed. Last response: {last_text}")


# Main request handler for chat endpoint (used by both Flask and Vercel serverless)
def handle_request(request):
    if request.method != "POST":
        return {
            "statusCode": 405,
            "body": "Method Not Allowed"
        }

    raw_body = getattr(request, "body", None)
    try:
        body = raw_body if isinstance(raw_body, dict) else json.loads(raw_body or "{}")
    except (TypeError, ValueError) as e:
        return {"statusCode": 400, "body": f"Invalid JSON body: {e}"}
    if not isinstance(body, dict):
        body = {}
    question = body.get("question")

    # Backwards compatible switch:
    # - allow_external: bool (legacy)
    # - mode: "strict" | "hybrid" | "general" (preferred)
    mode = body.get("mode")
    if not mode:
        mode = "hybrid" if body.get("allow_external", False) else "strict"

    if not question:
        log.warning("chat request missing question")
        return {
            "statusCode": 400,
            "body": "Missing question"
        }

    log.info("chat request mode=%s question_len=%s", mode, len(question))

    # Step 1: Generate embedding of question
    context_text = ""
    matches: List[Dict[str, Any]] = []

    if mode != "general":
        embedding = generate_embedding(question)

        # Step 2: Retrieve similar chunks from vector DB
        matches = [
            m for m in retrieve_chunks(embedding)
            if m.get("similarity", 0) >= SIMILARITY_THRESHOLD
        ]
        log.info("retrieved %s chunks above threshold", len(matches))

        # Step 3: Build context from retrieved chunks (cap length)
        context_text = "\n\n---\n\n".join([m.get("content", "") for m in matches]).strip()
        if len(context_text) > MAX_CONTEXT_CHARS:
            context_text = context_text[:MAX_CONTEXT_CHARS]

        # If strict mode and no matches found, return early
        if mode == "strict" and not matches:
            log.info("strict mode, no matches, returning no-answer")
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "answer": "I cannot find relevant information in the knowledge base for that question.",
                    "sources": [],
                    "mode": mode
                })
            }

    # Step 4: Generate answer using context and optionally external knowledge
    allow_external = (mode != "strict")
    answer = generate_answer(question, context_text, allow_external=allow_external)

    sources = build_sources_(matches)
    log.info("chat success mode=%s answer_len=%s sources=%s", mode, len(answer), len(sources))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "answer": answer,
            "mode": mode,
            "sources": sources
        })
    }


# Build sources metadata for response from matched chunks
def build_sources_(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not matches:
        return []

    doc_ids = sorted({m.get("doc_id") for m in matches if m.get("doc_id")})
    doc_map = fetch_documents_by_ids_(doc_ids)

    sources: List[Dict[str, Any]] = []
    for m in matches:
        doc_id = m.get("doc_id")
        doc = doc_map.get(doc_id, {}) if doc_id else {}

        content = m.get("content", "") or ""
        snippet = content[:240] + ("…" if len(content) > 240 else "")

        sources.append({
            "doc_id": doc_id,
            "title": doc.get("title"),
            "drive_url": doc.get("drive_url"),
            "chunk_index": m.get("chunk_index"),
            "similarity": m.get("similarity"),
            "snippet": snippet
        })

    return sources


# Fetch document metadata by IDs from Supabase
def fetch_documents_by_ids_(doc_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not doc_ids:
        return {}

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }

    # PostgREST "in" filter expects: id=in.(a,b,c)
    ids = ",".join(doc_ids)
    url = f"{SUPABASE_URL}/rest/v1/documents?id=in.({ids})&select=id,title,drive_url"

    res = requests.get(url, headers=headers, timeout=20)
    if res.status_code != 200:
        log.warning("fetch_documents_by_ids status=%s url=%s", res.status_code, url.split("?")[0])
        return {}

    rows = res.json()
    return {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}


# Generate embedding vector for given text
def generate_embedding(text):
    payload = {
        "content": {"parts": [{"text": text}]},
        "output_dimensionality": EMBED_DIM,
    }
    json_out = _gemini_post(EMBED_MODEL, "embedContent", payload)
    emb = json_out.get("embedding") or {}
    values = emb.get("values")
    if not values:
        raise RuntimeError("Gemini embedding response missing embedding.values")
    return values


# Retrieve matching chunks from Supabase vector DB
def retrieve_chunks(embedding):
    url = f"{SUPABASE_URL}/rest/v1/rpc/match_chunks"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "query_embedding": embedding,
        "match_count": MATCH_COUNT
    }

    res = requests.post(url, headers=headers, json=payload, timeout=20)
    res.raise_for_status()

    return res.json()


# Generate answer from question and context using Gemini model
def generate_answer(question, context, allow_external=False):
    if allow_external:
        instruction = (
            "You may use general knowledge in addition to the provided context, but clearly prioritise the context "
            "where relevant. If the context contains the answer, prefer it and cite it implicitly by referring to the "
            "provided sources."
        )
    else:
        instruction = (
            "You must answer using ONLY the context below. If the answer is not contained in the context, say you cannot "
            "find it in the knowledge base."
        )

    prompt = f"""You are a precise assistant.

{instruction}

Context:
{context}

Question:
{question}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 600,
            "temperature": 0.2,
        },
    }

    json_out = _gemini_post(CHAT_MODEL, "generateContent", payload)
    candidates = json_out.get("candidates") or []
    if not candidates:
        reason = (json_out.get("promptFeedback") or {}).get("blockReason") or "No candidates returned"
        raise RuntimeError(f"Gemini generateContent failed: {reason}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts or "text" not in parts[0]:
        raise RuntimeError("Gemini response missing text in first candidate")
    return parts[0]["text"]


# Vercel serverless: export handler class so /api/chat is served on Vercel
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length) if content_length else b""
            body_data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body_data = {}

        class Req:
            method = "POST"
            body = body_data

        try:
            out = handle_request(Req)
        except Exception as e:
            out = {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "The server ran into a problem while handling your question.",
                    "detail": str(e),
                }),
            }
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                out["body"] = json.dumps({
                    "error": "Gemini API rate limit reached.",
                    "detail": "Wait a minute and try again, or add GEMINI_API_KEY_2 in env.",
                })

        status = out.get("statusCode", 500)
        resp_body = out.get("body", "")
        if isinstance(resp_body, dict):
            resp_body = json.dumps(resp_body)
        if not isinstance(resp_body, str):
            resp_body = str(resp_body)

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(resp_body.encode("utf-8"))