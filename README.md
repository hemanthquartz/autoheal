# workflow_service.py
# -------------------------------------------------------------------------------------------------
# Runbook Orchestrator (Content-Understanding, Human-like Step Execution, Approval-Gated)
#
# What this file does:
#   - Loads Markdown runbooks from ./runbooks/*.md
#   - Chunks runbooks (headings-first, then sliding windows) to fit LLM context limits
#   - (Optional) Semantically pre-ranks runbooks/chunks if an embeddings client is provided
#   - Builds an LLM prompt with the alert + FULL runbook chunks (not just keywords)
#   - Requires the LLM to pick ONE runbook, justify with evidence, and produce atomic executable steps
#   - Executes steps ONE AT A TIME
#   - BEFORE each step execution, requests approval from Power Automate and waits for a decision
#   - Only when approval is ACCEPTED, triggers the Azure Function App to execute the step
#
# Security / deployment:
#   - DO NOT hardcode secrets (Power Automate sig tokens, function keys, etc.) in source control.
#   - Use App Settings / environment variables:
#       POWER_AUTOMATE_APPROVAL_URL (full invoke URL)
#       FUNCTION_APP_URL             (your Function App endpoint)
#       FUNCTION_APP_KEY             (optional, if not using ?code=)
#
# Notes:
#   - Per your earlier requirement: when executing a step, send ONLY RAW alert JSON to Function App.
#   - This file intentionally contains all logic in one place.
# -------------------------------------------------------------------------------------------------

import os
import glob
import re
import json
import time
import uuid
import math
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Union, List, Dict, Tuple, Any, Optional


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# -------------------------------------------------------------------------------------------------
# Configuration (set these via environment variables in Azure Web App Configuration)
# -------------------------------------------------------------------------------------------------

# Azure Function App (executor). Prefer env var, do NOT hardcode in repo.
FUNCTION_APP_URL = os.getenv("FUNCTION_APP_URL", "").strip()
FUNCTION_APP_KEY = os.getenv("FUNCTION_APP_KEY", "").strip()  # optional

# Power Automate approval endpoint (full invoke URL with query string).
# Put the full URL into App Settings env var POWER_AUTOMATE_APPROVAL_URL.
POWER_AUTOMATE_APPROVAL_URL = os.getenv("POWER_AUTOMATE_APPROVAL_URL", "").strip()

# Prompt shaping / prompt-size management
MAX_RUNBOOKS_IN_PROMPT = int(os.getenv("MAX_RUNBOOKS_IN_PROMPT", "60"))
MAX_CHARS_PER_CHUNK = int(os.getenv("MAX_CHARS_PER_CHUNK", "4500"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))

# If embeddings are available, narrow down to top K runbooks and then top M chunks/runbook
TOP_K_RUNBOOKS = int(os.getenv("TOP_K_RUNBOOKS", "20"))
TOP_M_CHUNKS_PER_RUNBOOK = int(os.getenv("TOP_M_CHUNKS_PER_RUNBOOK", "3"))
USE_EMBEDDINGS_PRESELECTION = os.getenv("USE_EMBEDDINGS_PRESELECTION", "true").lower() in ("1", "true", "yes")

# HTTP timeouts and retries
# Power Automate approval may take time; keep this high.
APPROVAL_HTTP_TIMEOUT_SECS = int(os.getenv("APPROVAL_HTTP_TIMEOUT_SECS", "1800"))  # 30 minutes
APPROVAL_MAX_ATTEMPTS = int(os.getenv("APPROVAL_MAX_ATTEMPTS", "3"))

# Function App execution timeout per call (increase if your function takes long).
FUNCTION_APP_TIMEOUT_SECS = int(os.getenv("FUNCTION_APP_TIMEOUT_SECS", "1800"))  # 30 minutes
FUNCTION_APP_MAX_ATTEMPTS = int(os.getenv("FUNCTION_APP_MAX_ATTEMPTS", "3"))

# If your web layer (Front Door / proxy) times out quickly, consider making step execution async
# outside of the request-response path. This file keeps synchronous "wait for approval" behavior.


# -------------------------------------------------------------------------------------------------
# Optional Embeddings Interface
# -------------------------------------------------------------------------------------------------

class EmbeddingsClient:
    """
    Optional interface for semantic pre-ranking.
    Implement embed_texts(texts: List[str]) -> List[List[float]] and pass an instance
    to run_github_workflow(...).
    """
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Provide an embeddings client or pass None")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-12
    nb = math.sqrt(sum(y * y for y in b)) or 1e-12
    return dot / (na * nb)


# -------------------------------------------------------------------------------------------------
# Utility helpers
# -------------------------------------------------------------------------------------------------

def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def force_json_dict(s: Any) -> Dict[str, Any]:
    """
    Try to coerce model 'content' to dict. Accept dict, JSON string, or fallback.
    """
    if isinstance(s, dict):
        return s
    if isinstance(s, str):
        try:
            return json.loads(s)
        except Exception:
            return {"summary": s, "params": {}}
    return {"summary": str(s), "params": {}}


def llm_process_with_retry(
    input_controller,
    payload: Dict[str, Any],
    format_type: str = "json",
    source: str = "splunk",
    max_attempts: int = 3
):
    """
    Calls input_controller.process with small exponential backoff on 429s.
    Returns the raw response or raises the last exception.
    """
    attempt = 0
    base_sleep = 0.6  # seconds
    while True:
        try:
            return input_controller.process(
                data=payload,
                format_type=format_type,
                source=source
            )
        except Exception as e:
            msg = str(e)
            retryable = ("429" in msg) or ("Rate limit" in msg) or ("rate limit" in msg)
            attempt += 1
            if (not retryable) or (attempt >= max_attempts):
                logger.error(f"LLM processing error (attempt {attempt}): {e}")
                raise
            sleep_for = base_sleep * (2 ** (attempt - 1)) + (0.1 * attempt)
            logger.warning(f"Rate limited; backing off for {sleep_for:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_for)


# -------------------------------------------------------------------------------------------------
# Runbook loading and chunking (NO keyword matching)
# -------------------------------------------------------------------------------------------------

def load_runbooks() -> List[Dict[str, Any]]:
    """
    Load Markdown runbooks from local ./runbooks/*.md
    Returns: list of dicts with keys: {id, title, content}
    """
    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    files = glob.glob(os.path.join(runbooks_dir, "*.md"))

    logger.info(f"[RUNBOOK] Looking for runbooks in: {runbooks_dir}")
    logger.info(f"[RUNBOOK] Found {len(files)} runbook files")

    runbooks: List[Dict[str, Any]] = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except Exception as e:
            logger.warning(f"[RUNBOOK] Skipping unreadable runbook file '{fpath}': {e}")
            continue

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

        rb = {"id": rb_id, "title": title, "content": content}
        runbooks.append(rb)

        logger.info(f"[RUNBOOK] Loaded | id={rb_id} | title={title} | content_len={len(content)}")

    logger.info(f"[RUNBOOK] Total loaded runbooks: {len(runbooks)}")
    return runbooks


def _split_by_headings(content: str) -> List[str]:
    """
    Split Markdown by top-level and second-level headings while preserving headings.
    """
    parts: List[str] = []
    buffer: List[str] = []
    lines = content.splitlines(keepends=True)

    def flush():
        if buffer:
            parts.append("".join(buffer).strip())
            buffer.clear()

    for line in lines:
        # # or ## at start (optionally preceded by up to 3 spaces)
        if re.match(r"^\s{0,3}#{1,2}\s", line):
            flush()
            buffer.append(line)
        else:
            buffer.append(line)

    flush()
    return [p for p in parts if p] or [content]


def _chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """
    Chunk content into ~max_chars segments with overlap to preserve context.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0
    end = len(text)

    while start < end:
        stop = min(start + max_chars, end)
        chunk = text[start:stop]
        chunks.append(chunk)
        if stop == end:
            break
        start = max(0, stop - overlap)

    return chunks


def chunk_runbook_content(content: str) -> List[str]:
    """
    Produce content chunks guided by headings first, then enforce size with sliding windows.
    Returns list of chunk strings (each within MAX_CHARS_PER_CHUNK).
    """
    sections = _split_by_headings(content)
    chunks: List[str] = []
    for sec in sections:
        chunks.extend(_chunk_text(sec, MAX_CHARS_PER_CHUNK, CHUNK_OVERLAP_CHARS))
    return chunks


# -------------------------------------------------------------------------------------------------
# Semantic pre-ranking (optional; NOT keyword-based)
# -------------------------------------------------------------------------------------------------

def rank_runbooks_semantically(
    alert_json: Dict[str, Any],
    runbooks: List[Dict[str, Any]],
    embeddings_client: Optional[EmbeddingsClient],
    k: int = TOP_K_RUNBOOKS
) -> List[Dict[str, Any]]:
    """
    If embeddings_client is provided and USE_EMBEDDINGS_PRESELECTION is True:
      - embed alert and full runbook content
      - return top-k runbooks by cosine similarity
    Else:
      - return runbooks unchanged
    """
    if not (embeddings_client and USE_EMBEDDINGS_PRESELECTION and runbooks):
        return runbooks

    try:
        alert_str = json.dumps(alert_json, ensure_ascii=False)
        alert_vec = embeddings_client.embed_texts([alert_str])[0]
        contents = [rb.get("content") or "" for rb in runbooks]
        rb_vecs = embeddings_client.embed_texts(contents)

        scored = []
        for rb, vec in zip(runbooks, rb_vecs):
            scored.append((_cosine(alert_vec, vec), rb))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = [rb for _, rb in scored[:k]]

        logger.info(f"[EMBED] Pre-ranked runbooks by content; selected {len(top)}/{len(runbooks)}")
        return top
    except Exception as e:
        logger.warning(f"[EMBED] Semantic pre-ranking failed, falling back to all runbooks: {e}")
        return runbooks


def rank_chunks_semantically(
    alert_json: Dict[str, Any],
    rb_id_to_chunks: Dict[str, List[str]],
    embeddings_client: Optional[EmbeddingsClient],
    top_m_per_runbook: int = TOP_M_CHUNKS_PER_RUNBOOK
) -> Dict[str, List[str]]:
    """
    Per runbook, rank its chunks by similarity to the alert. Return top M chunks per runbook.
    If no embeddings_client, return original chunks unchanged.
    """
    if not embeddings_client:
        return rb_id_to_chunks

    try:
        alert_str = json.dumps(alert_json, ensure_ascii=False)
        alert_vec = embeddings_client.embed_texts([alert_str])[0]

        top_chunks: Dict[str, List[str]] = {}
        for rb_id, chunks in rb_id_to_chunks.items():
            if not chunks:
                top_chunks[rb_id] = []
                continue

            vecs = embeddings_client.embed_texts(chunks)
            scored = [(_cosine(alert_vec, v), c) for v, c in zip(vecs, chunks)]
            scored.sort(key=lambda t: t[0], reverse=True)
            top_chunks[rb_id] = [c for _, c in scored[:top_m_per_runbook]]

        logger.info("[EMBED] Ranked chunks per runbook and selected top segments")
        return top_chunks
    except Exception as e:
        logger.warning(f"[EMBED] Chunk pre-ranking failed, using all chunks: {e}")
        return rb_id_to_chunks


# -------------------------------------------------------------------------------------------------
# LLM prompt construction (content-understanding, with evidence requirement)
# -------------------------------------------------------------------------------------------------

def build_instruction_for_structured_output(
    raw_message_str: str,
    runbook_payload: List[Dict[str, Any]]
) -> str:
    """
    Instruct the LLM to read the alert and FULL runbook content (chunked if needed),
    pick ONE runbook based on actual content, justify with evidence, and produce atomic steps.
    """
    rb_summaries: List[str] = []
    for rb in runbook_payload[:MAX_RUNBOOKS_IN_PROMPT]:
        rb_id = rb.get("id")
        title = rb.get("title")
        chunks = rb.get("chunks") or []
        parts = [f"RUNBOOK_ID: {rb_id}", f"TITLE: {title}", "CONTENT:"]
        for i, ch in enumerate(chunks):
            parts.append(f"<<CHUNK {i+1} START>>\n{ch}\n<<CHUNK {i+1} END>>")
        rb_summaries.append("\n".join(parts))

    runbooks_blob = "\n".join(rb_summaries) if rb_summaries else "NO RUNBOOKS PROVIDED"

    return (
        "You are an operations assistant.\n"
        "You will be given:\n"
        "1) An alert-like message (raw JSON/text)\n"
        "2) A set of runbooks with their FULL content included as chunks\n\n"
        "Your job:\n"
        "- Read the alert carefully.\n"
        "- Read the runbooks fully. Do NOT rely on titles or keywords alone.\n"
        "- Choose the SINGLE best matching runbook based on end-to-end content alignment with the alert.\n"
        "- Justify your choice with explicit, brief references to the runbook content: cite CHUNK numbers and headings.\n"
        "- Convert the chosen runbook into a HUMAN-LIKE ordered plan of steps. Each step must be atomic and executable.\n\n"
        "Rules:\n"
        "- Do NOT call tools.\n"
        "- Do NOT trigger actions directly.\n"
        "- If a field is unknown, use null.\n"
        "- steps must be a non-empty array if selected_runbook_id is not null.\n"
        "- If no runbook matches, selected_runbook_id must be null and steps may be an empty array.\n"
        "- Prefer content comprehension over keyword overlap. Cite the specific chunks that informed your decision.\n\n"
        "Return ONE JSON object with EXACTLY these fields:\n"
        "{\n"
        '  "summary": string,\n'
        '  "params": {\n'
        '    "cluster": string | null,\n'
        '    "namespace": string | null,\n'
        '    "service": string | null\n'
        "  },\n"
        '  "selected_runbook_id": string | null,\n'
        '  "selected_runbook_title": string | null,\n'
        '  "rationale": string,\n'
        '  "steps": [\n'
        "    {\n"
        '      "step": number,\n'
        '      "instruction": string,\n'
        '      "success_criteria": string,\n'
        '      "on_failure": string\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "ALERT RAW MESSAGE:\n"
        f"{raw_message_str}\n\n"
        "RUNBOOKS:\n"
        f"{runbooks_blob}\n"
    )


# -------------------------------------------------------------------------------------------------
# Power Automate approval (waits for Accepted/Rejected)
# -------------------------------------------------------------------------------------------------

def _parse_approval_response(resp_text: str) -> Dict[str, Any]:
    """
    Power Automate returns either:
      {"Status": "Accepted"}  OR  {"status": "Rejected"}
    We treat Accepted => approved True, Rejected => approved False.
    Also supports other common variants.
    """
    try:
        data = json.loads(resp_text)
        if isinstance(data, dict):
            raw_status = (
                data.get("Status")
                or data.get("status")
                or data.get("outcome")
                or data.get("Outcome")
                or data.get("result")
                or data.get("Result")
                or ""
            )
            status_norm = str(raw_status).strip().lower()

            if status_norm == "accepted":
                data["approved"] = True
                data["outcome"] = data.get("outcome") or data.get("Outcome") or "Accepted"
                return data

            if status_norm == "rejected":
                data["approved"] = False
                data["outcome"] = data.get("outcome") or data.get("Outcome") or "Rejected"
                return data

            # Fallback variants
            approved = data.get("approved")
            if approved is None:
                if status_norm in ("approve", "approved", "yes", "true"):
                    approved = True
                elif status_norm in ("reject", "rejected", "no", "false"):
                    approved = False

            if approved is None:
                approved = False

            data["approved"] = bool(approved)
            return data
    except Exception:
        pass

    t = (resp_text or "").strip().lower()
    if t in ("accepted", "approve", "approved", "yes", "true"):
        return {"approved": True, "outcome": "Accepted", "raw": resp_text}
    if t in ("rejected", "reject", "no", "false"):
        return {"approved": False, "outcome": "Rejected", "raw": resp_text}

    return {"approved": False, "outcome": "Unknown", "raw": resp_text}


def request_step_approval(
    approval_url: str,
    run_id: str,
    step_index: int,
    plan: Dict[str, Any],
    request_json: Dict[str, Any],
    timeout_secs: int = APPROVAL_HTTP_TIMEOUT_SECS,
    max_attempts: int = APPROVAL_MAX_ATTEMPTS
) -> Dict[str, Any]:
    """
    Calls Power Automate approval endpoint and waits for response.
    Expects response JSON to contain Status/status: Accepted/Rejected (case-insensitive).
    """
    if not approval_url:
        # If no approval URL is configured, default to "approved" to avoid blocking (you can change this).
        logger.warning("[APPROVAL] POWER_AUTOMATE_APPROVAL_URL not set; defaulting to approved=True")
        return {"approved": True, "outcome": "NoApprovalUrlConfigured"}

    steps = plan.get("steps") or []
    step_obj = steps[step_index] if 0 <= step_index < len(steps) else {}

    payload = {
        "run_id": run_id,
        "timestamp_utc": _now_iso_utc(),
        "selected_runbook_id": plan.get("selected_runbook_id"),
        "selected_runbook_title": plan.get("selected_runbook_title"),
        "step_index": step_index,
        "step": step_obj.get("step", step_index + 1),
        "instruction": step_obj.get("instruction"),
        "success_criteria": step_obj.get("success_criteria"),
        "on_failure": step_obj.get("on_failure"),
        # include a compact alert reference; keep raw alert available if your flow needs it
        "alert": request_json,
    }

    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "runbook-orchestrator/power-automate-approval"
    }

    attempt = 0
    last_err: Optional[RuntimeError] = None

    while attempt < max_attempts:
        attempt += 1
        req = urllib.request.Request(approval_url, data=body_bytes, headers=headers, method="POST")
        try:
            logger.info(f"[APPROVAL] Requesting approval | run_id={run_id} | step_index={step_index} | attempt={attempt}")
            with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
                status = resp.status
                resp_text = resp.read().decode("utf-8", errors="replace")
                parsed = _parse_approval_response(resp_text)

                logger.info(f"[APPROVAL] Response received | http={status} | approved={parsed.get('approved')} | outcome={parsed.get('outcome')}")
                parsed["_http_status"] = status
                parsed["_raw"] = resp_text
                return parsed

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            logger.error(f"[APPROVAL] HTTPError (attempt {attempt}/{max_attempts}): {e.code} {body}")
            last_err = RuntimeError(f"Approval endpoint HTTP error: {e.code} {body}")

            # Retry transient
            if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

        except urllib.error.URLError as e:
            logger.error(f"[APPROVAL] URLError (attempt {attempt}/{max_attempts}): {e}")
            last_err = RuntimeError(f"Approval endpoint connectivity error: {e}")
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

        except Exception as e:
            logger.error(f"[APPROVAL] Unexpected error (attempt {attempt}/{max_attempts}): {e}")
            last_err = RuntimeError(f"Approval endpoint unexpected error: {e}")
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

    if last_err:
        raise last_err
    raise RuntimeError("Approval request failed: unknown error")


# -------------------------------------------------------------------------------------------------
# Azure Function App trigger (accepts str or dict)
# -------------------------------------------------------------------------------------------------

def trigger_function_app(
    function_url: str,
    payload: Union[str, Dict[str, Any]],
    function_key: Optional[str] = None,
    max_attempts: int = FUNCTION_APP_MAX_ATTEMPTS,
    timeout_secs: int = FUNCTION_APP_TIMEOUT_SECS
) -> Tuple[int, str]:
    """
    POST payload to Azure Function App.
    - If payload is dict -> Content-Type: application/json
    - If payload is str  -> Content-Type: text/plain
    - Optionally uses x-functions-key header when URL doesn't include ?code=
    """
    if not function_url:
        raise RuntimeError("Function App URL is missing (set FUNCTION_APP_URL env var).")

    headers = {"User-Agent": "runbook-orchestrator/azure-function"}
    if isinstance(payload, dict):
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        headers["Content-Type"] = "text/plain"
        body_bytes = payload.encode("utf-8")
    else:
        raise TypeError(f"Unsupported payload type: {type(payload)}. Use str or dict.")

    # If caller passed function_key and URL doesn't already contain code=
    if function_key and ("code=" not in function_url):
        headers["x-functions-key"] = function_key

    attempt = 0
    last_err: Optional[RuntimeError] = None

    while attempt < max_attempts:
        attempt += 1
        req = urllib.request.Request(function_url, data=body_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
                status = resp.status
                resp_text = resp.read().decode("utf-8", errors="replace")
                logger.info(f"[FUNCTION_APP] Triggered successfully | status={status}")
                return status, resp_text

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            logger.error(f"[FUNCTION_APP] Trigger failed (attempt {attempt}/{max_attempts}): {e.code} {body}")
            last_err = RuntimeError(f"Function app trigger failed: {e.code} {body}")

            # Retry only on transient status codes
            if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

        except urllib.error.URLError as e:
            logger.error(f"[FUNCTION_APP] URL error (attempt {attempt}/{max_attempts}): {e}")
            last_err = RuntimeError(f"Function app trigger connectivity error: {e}")
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

        except Exception as e:
            logger.error(f"[FUNCTION_APP] Unexpected error (attempt {attempt}/{max_attempts}): {e}")
            last_err = RuntimeError(f"Function app trigger unexpected error: {e}")
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

    if last_err:
        raise last_err
    raise RuntimeError("Function app trigger failed: unknown error")


# -------------------------------------------------------------------------------------------------
# Step-by-step execution helpers (stateful across calls via request payload)
# -------------------------------------------------------------------------------------------------

def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex}"


def _get_execution_state(request_json: Dict[str, Any]) -> Dict[str, Any]:
    state = request_json.get("execution_state")
    if isinstance(state, dict):
        return state
    return {}


def _is_continuation_call(state: Dict[str, Any]) -> bool:
    return bool(state.get("run_id")) and isinstance(state.get("plan"), dict)


def _plan_has_more_steps(plan: Dict[str, Any], step_index: int) -> bool:
    steps = plan.get("steps") or []
    return step_index < len(steps)


def _execute_single_step_via_function_app(
    function_url: str,
    function_key: Optional[str],
    run_id: str,
    step_index: int,
    plan: Dict[str, Any],
    request_json: Dict[str, Any],
) -> Tuple[int, str]:
    """
    Executes exactly one step by calling the Azure Function App.
    PER REQUIREMENT: Always send ONLY the RAW alert JSON (request_json) to the Function App.
    """
    steps = plan.get("steps") or []
    if step_index >= len(steps):
        raise RuntimeError(f"Invalid step_index={step_index}, no step found")

    logger.info(
        f"[WORKFLOW] Executing step {step_index} using RAW payload only | "
        f"run_id={run_id} | selected_runbook_id={plan.get('selected_runbook_id')}"
    )

    # RAW payload path only (no runbook_step envelope)
    return trigger_function_app(
        function_url=function_url,
        payload=request_json,  # raw JSON without runbook_step envelope
        function_key=function_key,
        max_attempts=FUNCTION_APP_MAX_ATTEMPTS,
        timeout_secs=FUNCTION_APP_TIMEOUT_SECS,
    )


# -------------------------------------------------------------------------------------------------
# Main orchestrator
# -------------------------------------------------------------------------------------------------

def run_github_workflow(
    input_controller,
    request_json: Dict[str, Any],
    embeddings_client: Optional[EmbeddingsClient] = None,
) -> Dict[str, Any]:
    """
    Orchestrates:
      - If continuation call: approve + execute next step
      - Else: load runbooks, build plan via LLM, then approve + execute step 0

    Returns a response dict that includes updated execution_state.
    """

    # ---------------------------------------------------------------------------------------------
    # 1) Determine if this is a continuation call
    # ---------------------------------------------------------------------------------------------
    state = _get_execution_state(request_json)
    if _is_continuation_call(state):
        run_id = state["run_id"]
        plan = state["plan"]
        step_index = int(state.get("step_index", 0))

        logger.info(f"[WORKFLOW] Continuation call | run_id={run_id} | step_index={step_index}")

        if not _plan_has_more_steps(plan, step_index):
            logger.info(f"[WORKFLOW] No more steps | run_id={run_id}")
            return {
                "status": "completed",
                "message": "All steps completed.",
                "run_id": run_id,
                "plan": plan,
                "execution_state": {
                    "run_id": run_id,
                    "plan": plan,
                    "step_index": step_index,
                    "completed": True,
                    "timestamp_utc": _now_iso_utc()
                }
            }

        # Approval gate BEFORE executing this step
        approval = request_step_approval(
            approval_url=POWER_AUTOMATE_APPROVAL_URL,
            run_id=run_id,
            step_index=step_index,
            plan=plan,
            request_json=request_json,
        )

        if not approval.get("approved", False):
            logger.info(f"[WORKFLOW] Step blocked by approval | run_id={run_id} | step_index={step_index}")
            return {
                "status": "blocked",
                "message": "Step execution blocked by approval response.",
                "run_id": run_id,
                "plan": plan,
                "approval": approval,
                "execution_state": {
                    "run_id": run_id,
                    "plan": plan,
                    "step_index": step_index,
                    "blocked": True,
                    "timestamp_utc": _now_iso_utc()
                }
            }

        # Execute step
        http_status, resp_text = _execute_single_step_via_function_app(
            function_url=FUNCTION_APP_URL,
            function_key=FUNCTION_APP_KEY or None,
            run_id=run_id,
            step_index=step_index,
            plan=plan,
            request_json=request_json,
        )

        next_step_index = step_index + 1
        done = not _plan_has_more_steps(plan, next_step_index)

        return {
            "status": "completed" if done else "in_progress",
            "message": "Step executed." if not done else "Final step executed.",
            "run_id": run_id,
            "approval": approval,
            "function_app": {"http_status": http_status, "response": resp_text},
            "plan": plan,
            "execution_state": {
                "run_id": run_id,
                "plan": plan,
                "step_index": next_step_index,
                "completed": done,
                "timestamp_utc": _now_iso_utc()
            }
        }

    # ---------------------------------------------------------------------------------------------
    # 2) New run: build plan via LLM
    # ---------------------------------------------------------------------------------------------
    run_id = _new_run_id()
    logger.info(f"[WORKFLOW] New run | run_id={run_id}")

    runbooks = load_runbooks()

    # Pre-rank runbooks semantically (optional)
    runbooks = rank_runbooks_semantically(
        alert_json=request_json,
        runbooks=runbooks,
        embeddings_client=embeddings_client,
        k=TOP_K_RUNBOOKS
    )

    # Chunk runbooks
    rb_id_to_chunks: Dict[str, List[str]] = {}
    for rb in runbooks:
        rb_id_to_chunks[rb["id"]] = chunk_runbook_content(rb.get("content") or "")

    # Pre-rank chunks semantically (optional)
    rb_id_to_chunks = rank_chunks_semantically(
        alert_json=request_json,
        rb_id_to_chunks=rb_id_to_chunks,
        embeddings_client=embeddings_client,
        top_m_per_runbook=TOP_M_CHUNKS_PER_RUNBOOK
    )

    # Build runbook payload for LLM
    runbook_payload: List[Dict[str, Any]] = []
    for rb in runbooks:
        rb_id = rb["id"]
        runbook_payload.append({
            "id": rb_id,
            "title": rb.get("title"),
            "chunks": rb_id_to_chunks.get(rb_id, [])
        })

    raw_message_str = json.dumps(request_json, ensure_ascii=False, indent=2)
    instruction = build_instruction_for_structured_output(raw_message_str, runbook_payload)

    # Call LLM
    llm_payload = {
        "type": "user_message",
        "content": instruction,
        "conversation_id": "",
        "timestamp": _now_iso_utc(),
        "source": "web_ui"
    }

    llm_resp = llm_process_with_retry(
        input_controller=input_controller,
        payload=llm_payload,
        format_type="json",
        source="web_ui",
        max_attempts=3
    )

    # Extract plan dict from response
    # Many controllers return {"content": "..."}; some return already parsed dict.
    plan = force_json_dict(llm_resp.get("content") if isinstance(llm_resp, dict) else llm_resp)

    # Validate plan shape
    selected_runbook_id = plan.get("selected_runbook_id")
    steps = plan.get("steps") or []
    if selected_runbook_id and not steps:
        logger.warning("[WORKFLOW] LLM selected a runbook but produced no steps. Marking as no_match.")
        plan["selected_runbook_id"] = None
        plan["selected_runbook_title"] = None

    if not plan.get("selected_runbook_id"):
        logger.info("[WORKFLOW] No matching runbook selected.")
        return {
            "status": "no_match",
            "message": "No matching runbook selected by the model.",
            "run_id": run_id,
            "plan": plan,
            "execution_state": {
                "run_id": run_id,
                "plan": plan,
                "step_index": 0,
                "completed": True,
                "timestamp_utc": _now_iso_utc()
            }
        }

    # ---------------------------------------------------------------------------------------------
    # 3) Execute step 0 (approval-gated)
    # ---------------------------------------------------------------------------------------------
    step_index = 0
    approval = request_step_approval(
        approval_url=POWER_AUTOMATE_APPROVAL_URL,
        run_id=run_id,
        step_index=step_index,
        plan=plan,
        request_json=request_json,
    )

    if not approval.get("approved", False):
        logger.info(f"[WORKFLOW] Step blocked by approval | run_id={run_id} | step_index={step_index}")
        return {
            "status": "blocked",
            "message": "Step execution blocked by approval response.",
            "run_id": run_id,
            "plan": plan,
            "approval": approval,
            "execution_state": {
                "run_id": run_id,
                "plan": plan,
                "step_index": step_index,
                "blocked": True,
                "timestamp_utc": _now_iso_utc()
            }
        }

    http_status, resp_text = _execute_single_step_via_function_app(
        function_url=FUNCTION_APP_URL,
        function_key=FUNCTION_APP_KEY or None,
        run_id=run_id,
        step_index=step_index,
        plan=plan,
        request_json=request_json,
    )

    next_step_index = step_index + 1
    done = not _plan_has_more_steps(plan, next_step_index)

    return {
        "status": "completed" if done else "in_progress",
        "message": "Step executed." if not done else "Final step executed.",
        "run_id": run_id,
        "approval": approval,
        "function_app": {"http_status": http_status, "response": resp_text},
        "plan": plan,
        "execution_state": {
            "run_id": run_id,
            "plan": plan,
            "step_index": next_step_index,
            "completed": done,
            "timestamp_utc": _now_iso_utc()
        }
    }
