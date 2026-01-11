Below is **everything (corrections + debugging additions)** in one go: **updated `load_runbooks()`**, **updated `match_runbooks()`**, and **the debugging additions inside `github_workflow()`**, plus **2 small helper functions**.

✅ This will tell you *exactly* why no runbook was selected:

* Were runbooks loaded?
* What keywords were extracted?
* What “match text” was built from summary + params?
* Which runbooks got which score?
* Which keywords matched (or not)?

---

## 0) Add these imports (if not already present)

```python
import os, re, glob, json
from flask import request, jsonify, current_app
```

---

## 1) Add these helpers (new)

```python
def _normalize_for_match(s: str) -> str:
    """
    Normalize strings for keyword matching:
    - lowercase
    - replace non-alphanumeric with spaces
    - collapse whitespace
    This fixes issues like AppReadiness vs appreadiness, punctuation, etc.
    """
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def parse_dimensions_kv(dimensions: str) -> dict:
    """
    Parse a SignalFx-style 'dimensions' blob:
    "{k=v, a=b, ...}" -> dict. Splits on commas, then first '='.

    NOTE: This is simple and works for your current alert format.
    """
    if not dimensions:
        return {}

    s = dimensions.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]

    out = {}
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out
```

---

## 2) Replace your `load_runbooks()` with this (updated + debug)

```python
def load_runbooks():
    """
    Load Markdown runbooks from local './runbooks/*.md'

    Returns: list of dicts with keys: {id, title, content, keywords}
    Debug: Logs what was loaded and what keywords were derived.
    """
    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    files = glob.glob(os.path.join(runbooks_dir, "*.md"))

    logger.info(f"[RUNBOOK_DEBUG] Looking for runbooks in: {runbooks_dir}")
    logger.info(f"[RUNBOOK_DEBUG] Found {len(files)} runbook files: {files}")

    runbooks = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except Exception as e:
            logger.warning(f"[RUNBOOK_DEBUG] Skipping unreadable runbook file '{fpath}': {e}")
            continue

        # id from filename (without extension)
        fname = os.path.basename(fpath)
        rb_id = os.path.splitext(fname)[0]

        # Title: first H1 '# ' if present; else filename-derived
        title = None
        for line in content.splitlines():
            l = line.lstrip("\ufeff").strip()
            if l.startswith("# "):
                title = l[2:].strip()
                break
        if not title:
            title = re.sub(r"[_\-]+", " ", rb_id).strip().title()

        # Base keywords from filename tokens
        raw_tokens = re.split(r"[^A-Za-z0-9]+", rb_id)
        keywords = [t.lower() for t in raw_tokens if t]

        # NEW: add title tokens too (helps a lot)
        title_tokens = re.split(r"[^A-Za-z0-9]+", title)
        keywords.extend([t.lower() for t in title_tokens if t])

        # OPTIONAL: enrich keywords from a 'Keywords:' line
        m = re.search(r"(?i)^keywords:\s*(.+)$", content, flags=re.MULTILINE)
        if m:
            extra = [k.strip().lower() for k in m.group(1).split(",") if k.strip()]
            keywords.extend(extra)

        # Normalize/dedupe keywords
        keywords = sorted(set([k for k in keywords if k]))

        rb = {
            "id": rb_id,
            "title": title,
            "content": content,
            "keywords": keywords
        }
        runbooks.append(rb)

        # Debug logs (do NOT print whole content)
        logger.info(
            f"[RUNBOOK_DEBUG] Loaded runbook | id={rb_id} | title={title} "
            f"| keywords={keywords} | content_len={len(content)}"
        )

    logger.info(f"[RUNBOOK_DEBUG] Total loaded runbooks: {len(runbooks)}")
    return runbooks
```

---

## 3) Replace your `match_runbooks()` with this (updated + deep debug)

```python
def match_runbooks(alert_summary, params, runbooks):
    """
    Deterministic matching: keyword scoring against summary + ALL param values.
    Debug: logs scoring, matched keywords, and the final decision.
    """
    logger.info("[RUNBOOK_DEBUG] --- match_runbooks START ---")

    # Build haystack from summary + param values
    parts = []
    if alert_summary:
        parts.append(str(alert_summary))

    if isinstance(params, dict):
        for k, v in params.items():
            if v is None:
                continue
            parts.append(str(v))
            logger.info(f"[RUNBOOK_DEBUG] Match input param | {k}={v}")

    haystack_raw = " ".join(parts)
    haystack = _normalize_for_match(haystack_raw)

    logger.info(f"[RUNBOOK_DEBUG] Alert summary: {alert_summary}")
    logger.info(f"[RUNBOOK_DEBUG] Haystack(raw): {haystack_raw}")
    logger.info(f"[RUNBOOK_DEBUG] Haystack(norm): {haystack}")

    if not runbooks:
        logger.warning("[RUNBOOK_DEBUG] No runbooks provided to match_runbooks()")
        return []

    ranked = []
    for rb in runbooks:
        score = 0
        matched_keywords = []

        rb_keywords = rb.get("keywords", []) or []
        if not rb_keywords:
            logger.warning(f"[RUNBOOK_DEBUG] Runbook '{rb.get('id')}' has NO keywords")
        else:
            logger.info(f"[RUNBOOK_DEBUG] Runbook '{rb.get('id')}' keywords={rb_keywords}")

        for kw in rb_keywords:
            kw_norm = _normalize_for_match(kw)
            if kw_norm and kw_norm in haystack:
                score += 1
                matched_keywords.append(kw)

        ranked.append((score, rb, matched_keywords))
        logger.info(
            f"[RUNBOOK_DEBUG] Score | runbook={rb.get('id')} | score={score} | matched={matched_keywords}"
        )

    # Sort by score desc
    ranked.sort(key=lambda x: x[0], reverse=True)

    # Filter to score>0; if none, return empty (so you can see the failure clearly)
    filtered = [rb for score, rb, _mk in ranked if score > 0]

    logger.info(f"[RUNBOOK_DEBUG] Ranked(top5)={[(s, r.get('id')) for s, r, _ in ranked[:5]]}")
    logger.info(f"[RUNBOOK_DEBUG] Filtered matches (score>0)={[rb.get('id') for rb in filtered]}")

    logger.info("[RUNBOOK_DEBUG] --- match_runbooks END ---")
    return filtered[:3]
```

> If you want “always select something”, tell me and I’ll add a controlled fallback.
> For now, this keeps it strict so the debug clearly shows why selection is empty.

---

## 4) Add these debug additions inside `github_workflow()` (the key points)

Below is a **drop-in block** to add/adjust inside your route **after you compute `extracted_params` and `alert_summary`** and before you build `proposal`.

```python
# -------------------------
# RUNBOOK LOAD + MATCH (with debug)
# -------------------------
runbooks = load_runbooks()
logger.info(f"[RUNBOOK_DEBUG] github_workflow: loaded_runbooks={len(runbooks)}")

# Add this: show normalized match inputs (helps a LOT)
logger.info(f"[RUNBOOK_DEBUG] github_workflow: alert_summary(norm)={_normalize_for_match(alert_summary)}")
logger.info(f"[RUNBOOK_DEBUG] github_workflow: params={extracted_params}")

matched = match_runbooks(
    alert_summary=alert_summary,
    params=extracted_params,
    runbooks=runbooks
)

logger.info(f"[RUNBOOK_DEBUG] github_workflow: matched_count={len(matched)}")
for rb in matched:
    logger.info(f"[RUNBOOK_DEBUG] github_workflow: matched_runbook id={rb.get('id')} title={rb.get('title')}")

suggested_runbooks = [
    {"id": rb["id"], "title": rb["title"], "content": rb["content"]}
    for rb in matched
] if matched else []

selected_runbook = suggested_runbooks[0] if suggested_runbooks else None

if not selected_runbook:
    logger.warning(
        "[RUNBOOK_DEBUG] No runbook selected. "
        f"loaded={len(runbooks)} matched={len(matched)} "
        "=> likely keyword mismatch. Check RUNBOOK_DEBUG scoring lines."
    )
```

---

# 5) The most common reason this still won’t match

Your runbook **must have keywords that exist in the normalized haystack**.

From your response, the haystack includes words like:

* `windows`
* `appreadiness`
* `restart`
* `azure`
* `vm`
* `pih jboxqa grn`

So make sure your runbook file includes:

```md
Keywords: restart, windows, service, appreadiness, azure, vm
```

Even if your runbook id is `restart_windows_service`, adding `appreadiness` helps the score go > 0 immediately.

---

## What to do now

1. Deploy these method changes
2. Trigger the same payload again
3. Paste ONLY the log lines starting with `[RUNBOOK_DEBUG]`

I’ll pinpoint the exact mismatch (it will usually be: keywords missing OR runbooks directory path is wrong OR keywords line not being parsed).
