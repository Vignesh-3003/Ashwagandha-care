# AshwaCare — The Complete Ashwagandha Guide (Python / Flask)

One plant only: **Ashwagandha** (*Withania somnifera*, Indian ginseng).
Built as a Python web app — Flask routes, Jinja templates, Pillow for images, `requests` for the
vision model. No Node, no build step.

## What the app does

| Section | What it is |
|---|---|
| Hero | 3D Ashwagandha plant (Three.js, bundled locally): leaves, orange-red berries in papery calyces, tapered root. **Drag to spin 360°**, momentum on release, scroll to zoom, double-click to reset, arrow keys for keyboard. SVG fallback if WebGL is unavailable. |
| Overview | What the plant is, where it grows, why one plant only. |
| Growing guide | Seven-step timeline: climate, soil, sowing, spacing, care, harvest, after harvest. |
| Problem explorer | Five problems with symptoms, cause, treatment, prevention; the symptom filter highlights the matching cards. |
| Leaf scan | Photo up to **30 MB**. On-device scan runs first in the browser; if the Flask server is up, a vision model adds a second reading (its own sentences, the evidence, runner-ups, damage estimate). |
| Uses & safety | Root powder, capsules, tea, warm milk, plus the safety card. |
| Tips & FAQ | Four-question accordion and three field tips. |

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                          # http://localhost:5000
```

With no key the app starts on the **demo provider**: the plumbing is real, the diagnosis is a
labelled placeholder. For real readings:

```bash
cp .env.example .env
# in .env:  PROVIDER=gemini   and   GEMINI_API_KEY=your-key
# or PROVIDER=openai + OPENAI_API_KEY, or PROVIDER=anthropic + ANTHROPIC_API_KEY
```

The chip above the scanner turns from *Demo AI* to *Cloud AI ready*.

Production:

```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

Docker:

```bash
docker build -t ashwacare .
docker run -p 5000:5000 --env-file .env ashwacare
```

## Project layout

```
app.py                  Flask app: routes, rate limiting, LRU cache, error handlers
config.py               settings from environment / .env
knowledge.py            the five problems + healthy (shared by prompt and UI)
services/imaging.py     Pillow: format check, EXIF strip, downscale to 1600 px, JPEG re-encode
services/vision.py      Gemini / OpenAI / Anthropic / mock adapters + strict output validation
templates/index.html    the page, rendered by Jinja ({{ max_mb }}, {{ year }}, {{ api_base }})
static/css/style.css    stylesheet
static/js/app.js        page script: 3D plant, problem filter, accordion, leaf scanner
static/vendor/          three.module.js, bundled so the 3D needs no CDN
tests/test_api.py       pytest suite (15 checks)
test_ui.js              optional headless-browser check (needs Node + puppeteer)
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | the guide, rendered from the template |
| `GET /api/health` | provider, model, `maxImageMB`, the six condition keys |
| `POST /api/analyze` | multipart `image` (or JSON `imageBase64`) → condition, confidence, differential, evidence, narrative, severity_pct |
| `POST /api/chat` | `{ message, condition, history }` → a grounded follow-up answer |

Errors: `413 too_large` (with `maxMB`), `415 unsupported_type`, `422 undecodable`,
`429 rate_limited`, `502 model_error`. The page treats every one as "keep the on-device result".

## Tests

```bash
pytest -q                 # 15 API checks, no key needed
node test_ui.js           # 12 browser checks (page, 3D drag, cloud AI, 30 MB limit)
```

## Configuration

`HOST`, `PORT`, `PROVIDER`, `MODEL`, `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`,
`MAX_IMAGE_MB` (30), `MAX_EDGE_PX` (1600), `JPEG_QUALITY`, `RATE_ANALYZE` / `RATE_CHAT`,
`CACHE_MAX` / `CACHE_TTL_MS`, `ALLOWED_ORIGINS`, `API_BASE`, `MODEL_TIMEOUT_MS`.
See `.env.example`.

## Notes

- **Images are never stored.** Uploads are read into memory, re-encoded, sent once, and dropped.
  EXIF (including GPS) is removed by the re-encode.
- **HEIC from iPhones** needs the optional `pillow-heif` package (see `requirements.txt`).
- **three.js is vendored** at `static/vendor/three.module.js`, so the 3D scene works offline; two
  CDNs remain as a fallback if that file is missing.
- The scan is visual screening, not a laboratory test. For any chemical, follow the product label
  and your local agriculture officer. Nothing here is medical advice.
