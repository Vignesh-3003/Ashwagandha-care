"""AshwaCare — a Flask app for one plant: Ashwagandha (Withania somnifera).

Routes
    GET  /              the guide, rendered from templates/index.html
    GET  /api/health    which engine is live, and the limits the page shows
    POST /api/analyze   one leaf photo in, a structured reading out
    POST /api/chat      a follow-up question about that reading

The page keeps its own on-device scan, so it works with the server switched off.
When the server answers, a vision model adds a second reading; anything that
fails leaves the local answer in place.

Run:  python app.py           (http://localhost:5000, demo provider by default)
      PROVIDER=gemini GEMINI_API_KEY=... python app.py
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import Config
from knowledge import KEYS, is_condition
from services import imaging, vision

app = Flask(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
app.json.sort_keys = False


# ---------------------------------------------------------------------------
# rate limiting — fixed windows per IP, fine for one process
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        """Return (allowed, remaining, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            count, reset_at = self._hits.get(key, (0, now + self.window))
            if now > reset_at:
                count, reset_at = 0, now + self.window
            count += 1
            self._hits[key] = (count, reset_at)
            # opportunistic cleanup so the dict cannot grow without bound
            if len(self._hits) > 4096:
                for stale in [k for k, (_, reset) in self._hits.items() if reset < now]:
                    self._hits.pop(stale, None)
        allowed = count <= self.limit
        return allowed, max(0, self.limit - count), int(max(0, reset_at - now))


analyze_limiter = RateLimiter(Config.RATE_ANALYZE, Config.RATE_WINDOW_SECONDS)
chat_limiter = RateLimiter(Config.RATE_CHAT, Config.RATE_WINDOW_SECONDS)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or "unknown"


def _rate_limited(limiter: RateLimiter):
    allowed, remaining, retry_after = limiter.check(_client_ip())
    if allowed:
        return None
    response = jsonify(
        error="rate_limited",
        message="Too many scans from this connection. Try again shortly.",
    )
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


# ---------------------------------------------------------------------------
# small LRU cache, keyed by the hash of the uploaded bytes
# ---------------------------------------------------------------------------
class ResultCache:
    def __init__(self, max_items: int, ttl_seconds: float) -> None:
        self.max_items = max_items
        self.ttl = ttl_seconds
        self._items: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._items.get(key)
            if not entry:
                return None
            value, expires = entry
            if time.time() > expires:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._items[key] = (value, time.time() + self.ttl)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)


cache = ResultCache(Config.CACHE_MAX, Config.CACHE_TTL_SECONDS)


# ---------------------------------------------------------------------------
# headers: CORS when configured, plus the small hardening defaults
# ---------------------------------------------------------------------------
@app.after_request
def add_headers(response):
    origin = request.headers.get("Origin")
    allowed = Config.ALLOWED_ORIGINS
    if origin and ("*" in allowed or origin in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Max-Age"] = "86400"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.route(
    "/api/<path:_rest>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def api_catch_all(_rest: str):
    """Unknown /api paths get JSON, never an HTML error page; CORS preflight gets 204."""
    if request.method == "OPTIONS":
        return ("", 204)
    return (
        jsonify(
            error="not_found",
            message=f"No such endpoint: {request.method} {request.path}",
        ),
        404,
    )


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    """The whole guide, rendered by Jinja."""
    return render_template(
        "index.html",
        max_mb=Config.MAX_IMAGE_MB,
        year=time.localtime().tm_year,
        api_base=Config.API_BASE,
        conditions=[{"key": k, "name": vision.CONDITIONS[k]["name"]} for k in KEYS],
    )


@app.get("/robots.txt")
def robots():
    return app.response_class("User-agent: *\nAllow: /\n", mimetype="text/plain")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        ok=True,
        service="ashwacare",
        version="1.0.0",
        plant="Withania somnifera",
        provider=vision.PROVIDER,
        model=vision.MODEL,
        demo=vision.IS_DEMO,
        maxImageMB=Config.MAX_IMAGE_MB,
        maxEdgePx=Config.MAX_EDGE_PX,
        conditions=KEYS,
        limits={"analyzePer15min": Config.RATE_ANALYZE, "chatPer15min": Config.RATE_CHAT},
        time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def _read_upload() -> tuple[bytes, str]:
    """Accept multipart field `image` or a JSON body with base64."""
    if "image" in request.files:
        uploaded = request.files["image"]
        return uploaded.read(), (request.form.get("note") or "").strip()

    payload = request.get_json(silent=True) or {}
    encoded = payload.get("imageBase64") or payload.get("image")
    if encoded:
        if "," in encoded[:64] and encoded.lstrip().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        try:
            import base64

            return base64.b64decode(encoded, validate=False), str(payload.get("note") or "").strip()
        except (ValueError, TypeError):
            raise imaging.ImageError("bad_base64", "The base64 image could not be decoded.", 400)

    return b"", ""


@app.post("/api/analyze")
def analyze():
    limited = _rate_limited(analyze_limiter)
    if limited:
        return limited

    try:
        raw, note = _read_upload()
    except imaging.ImageError as exc:
        return jsonify(error=exc.code, message=exc.message), exc.status

    if not raw:
        return (
            jsonify(
                error="no_image",
                message='Send the photo as multipart field "image" or as JSON { imageBase64 }.',
            ),
            400,
        )

    try:
        prepared = imaging.prepare(raw)
    except imaging.ImageError as exc:
        body = {"error": exc.code, "message": exc.message}
        if exc.code == "too_large":
            body["maxMB"] = Config.MAX_IMAGE_MB
        return jsonify(body), exc.status

    cached = cache.get(prepared["sha256"])
    if cached:
        return jsonify({**cached, "cached": True})

    try:
        result = vision.analyze_image(prepared, note)
    except vision.ModelError as exc:
        app.logger.warning("analyze failed: %s", exc)
        return (
            jsonify(
                error="model_error",
                message="The vision model did not return a usable answer. "
                "The on-device scan still applies.",
            ),
            502,
        )

    payload = {
        **result,
        "engine": "cloud",
        "analysed": {
            "width": prepared["width"],
            "height": prepared["height"],
            "bytes": prepared["bytes"],
            "sentBytes": prepared["original_bytes"],
        },
        "cached": False,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    cache.put(prepared["sha256"], payload)
    return jsonify(payload)


@app.post("/api/chat")
def chat():
    limited = _rate_limited(chat_limiter)
    if limited:
        return limited

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify(error="empty_message", message="Ask a question first."), 400
    if len(message) > 800:
        return jsonify(error="too_long", message="Keep the question under 800 characters."), 400

    condition = payload.get("condition") if is_condition(payload.get("condition")) else None
    try:
        reply = vision.chat(message, condition, payload.get("history"))
    except vision.ModelError as exc:
        app.logger.warning("chat failed: %s", exc)
        return jsonify(error="model_error", message="The assistant is not answering right now."), 502

    return jsonify(
        reply=reply,
        provider=vision.PROVIDER,
        demo=vision.IS_DEMO,
        at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
@app.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    message = f"That upload is over the {Config.MAX_IMAGE_MB} MB limit."
    if request.path.startswith("/api/"):
        return jsonify(error="too_large", maxMB=Config.MAX_IMAGE_MB, message=message), 413
    return message, 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return (
            jsonify(
                error="not_found",
                message=f"No such endpoint: {request.method} {request.path}",
            ),
            404,
        )
    return "Not found", 404


@app.errorhandler(HTTPException)
def http_error(error: HTTPException):
    if request.path.startswith("/api/"):
        return jsonify(error=error.name.lower().replace(" ", "_"), message=error.description), error.code or 500
    return error


@app.errorhandler(Exception)
def unhandled(error: Exception):
    app.logger.exception("unhandled error: %s", error)
    if request.path.startswith("/api/"):
        return jsonify(error="server_error", message="Something went wrong on the server."), 500
    return "Something went wrong on the server.", 500


if __name__ == "__main__":
    banner = "DEMO (no model key — set PROVIDER + a key)" if vision.IS_DEMO else vision.PROVIDER
    print()
    print("  AshwaCare — Flask")
    print("  ----------------")
    print(f"  url      http://localhost:{Config.PORT}")
    print(f"  engine   {banner}  ·  model {vision.MODEL}")
    print(f"  uploads  up to {Config.MAX_IMAGE_MB} MB, downscaled to {Config.MAX_EDGE_PX} px before the model")
    print()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
