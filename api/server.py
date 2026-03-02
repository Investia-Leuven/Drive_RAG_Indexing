"""
Minimal Flask server to run the RAG chat backend locally.
Run from project root: python -m api.server
Then open the frontend (e.g. npm run dev in frontend/) and use the chat.
"""
import json
import logging
from flask import Flask, request, Response

# Load .env before importing chat (chat reads os.environ at import)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

from api.chat import handle_request

app = Flask(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


@app.route("/")
def index():
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>RAG Backend</title></head><body>"
        "<h1>Backend is running</h1>"
        "<p>This is the API server. Use the <strong>chat app</strong> at "
        "<a href='http://localhost:5173'>http://localhost:5173</a> (run <code>npm run dev</code> in the <code>frontend</code> folder first).</p>"
        "<p><a href='/api/health'>/api/health</a> – check API status</p>"
        "</body></html>"
    ), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS
    return Response(json.dumps({"ok": True}), status=200, headers={**CORS_HEADERS, "Content-Type": "application/json"})


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS

    log.info("POST /api/chat")
    try:
        class Req:
            method = request.method
            body = request.get_json(silent=True) or request.get_data(as_text=True) or "{}"

        out = handle_request(Req)
        status = out.get("statusCode", 500)
        headers = {**dict(out.get("headers") or {}), **CORS_HEADERS}
        body = out.get("body", "")
        if isinstance(body, dict):
            body = json.dumps(body)
        log.info("POST /api/chat response status=%s", status)
        return Response(body, status=status, headers=headers, mimetype="application/json")
    except Exception as e:
        log.exception("chat handler failed: %s", e)
        err_msg = str(e)
        is_quota = "429" in err_msg or "quota" in err_msg.lower() or "RESOURCE_EXHAUSTED" in err_msg
        if is_quota:
            payload = {
                "error": "Gemini API rate limit reached. You’ve hit the free-tier quota for this minute or day.",
                "detail": "Quota exceeded (429). Wait a minute and try again, or add a second key as GEMINI_API_KEY_2 in .env for fallback.",
            }
        else:
            payload = {
                "error": "The server ran into a problem while handling your question.",
                "detail": err_msg,
            }
        return Response(
            json.dumps(payload),
            status=500,
            headers={**CORS_HEADERS, "Content-Type": "application/json"},
        )


if __name__ == "__main__":
    app.run(port=5000, debug=True)
