# workflow_service.py

import os
import glob
import re
import json
import logging
import urllib.request
import urllib.error
import time
import uuid
from datetime import datetime, timezone
from typing import Union, List, Dict, Tuple, Any, Optional

logger = logging.getLogger(__name__)

# Hard-coded Function App URL (use placeholder; do NOT hardcode secrets here)
# If you use a function key, prefer x-functions-key header (function_key param in trigger_function_app)
FUNCTION_APP_URL = (
    "https://<your-functionapp>.azurewebsites.net/api/<your-endpoint>"
    # If you currently rely on ?code= in URL, keep it outside source control and inject via env/config instead.
)

# --------------------------
# Helpers / utilities
# --------------------------

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
            # Heuristics: treat explicit 429 or vendor rate-limit messages as retryable
            retryable = ("429" in msg) or ("Rate limit" in msg) or ("rate limit" in msg)
            attempt += 1
            if (not retryable) or (attempt >= max_attempts):
                logger.error(f"LLM processing error (attempt {attempt}): {e}")
                raise

            # Backoff with jitter
            sleep_for = base_sleep * (2 ** (attempt - 1)) + (0.1 * attempt)
            logger.warning(
                f"Rate limited; backing off for {sleep_for:.2f}s (attempt {attempt}/{max_attempts})"
            )
            time.sleep(sleep_for)


def load_runbooks() -> List[Dict[str, Any]]:
    """
    Load Markdown runbooks from local './runbooks/*.md'

    Returns: list of dicts with keys: {id, title, content, keywords}
    Debug: Logs what was loaded and what keywords were derived.
    """
    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    files = glob.glob(os.path.join(runbooks_dir, "*.md"))

    logger.info(f"[RUNBOOK_DEBUG] Looking for runbooks in: {runbooks_dir}")
    logger.info(f"[RUNBOOK_DEBUG] Found {len(files)} runbook files: {files}")

    runbooks: List[Dict[str, Any]] = []

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

        # Base keywords from filename tokens + title tokens + optional 'keywords:' line
        raw_tokens = re.split(r"[^A-Za-z0-9]+", rb_id)
        keywords = [t.lower() for t in raw_tokens if t]

        title_tokens = re.split(r"[^A-Za-z0-9]+", title)
        keywords.extend([t.lower() for t in title_tokens if t])

        m = re.search(r"(?i)^keywords:\s*(.+)$", content, flags=re.MULTILINE)
        if m:
            extra = [k.strip().lower() for k in m.group(1).split(",") if k.strip()]
            keywords.extend(extra)

        keywords = sorted(set([k for k in keywords if k]))

        rb = {
            "id": rb_id,
            "title": title,
            "content": content,
            "keywords": keywords
        }
        runbooks.append(rb)

        logger.info(
            f"[RUNBOOK_DEBUG] Loaded runbook | id={rb_id} | title={title} | "
            f"keywords={keywords} | content_len={len(content)}"
        )

    logger.info(f"[RUNBOOK_DEBUG] Total loaded runbooks: {len(runbooks)}")
    return runbooks


def _normalize_for_match(s: str) -> str:
    """
    Normalize strings for keyword matching:
    - lowercase
    - replace non-alphanumeric with spaces
    - collapse whitespace
    """
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def match_runbooks(
    alert_summary: str,
    params: Dict[str, Any],
    runbooks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Deterministic matching: keyword scoring against summary + ALL param values.
    Debug: logs scoring, matched keywords, and the final decision.
    """
    logger.info("[RUNBOOK_DEBUG] --- match_runbooks START ---")

    parts: List[str] = []
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

    ranked: List[Tuple[int, Dict[str, Any], List[str]]] = []
    for rb in runbooks:
        score = 0
        matched_keywords: List[str] = []

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

    ranked.sort(key=lambda x: x[0], reverse=True)
    filtered = [rb for score, rb, _mk in ranked if score > 0]

    logger.info(f"[RUNBOOK_DEBUG] Ranked(top5)={[(s, r.get('id')) for s, r, _ in ranked[:5]]}")
    logger.info(f"[RUNBOOK_DEBUG] Filtered matches(score>0)={[rb.get('id') for rb in filtered]}")
    logger.info(f"[RUNBOOK_DEBUG] --- match_runbooks END ---")
    return filtered[:3]


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


# --------------------------
# LLM plan generation prompt
# --------------------------

def build_instruction_for_structured_output(raw_message_str: str, runbooks: List[Dict[str, Any]]) -> str:
    """
    Instruct the LLM to:
      - analyze the alert-like message
      - read provided runbooks (unstructured allowed)
      - pick the best runbook (or none)
      - produce a step-by-step execution plan (human-like)
    """

    # Keep runbook payload bounded to reduce prompt blow-ups.
    # Include id/title + a trimmed portion of content (still enough for the model to infer steps).
    rb_summaries: List[str] = []
    for rb in runbooks[:30]:  # safeguard: do not send unlimited runbooks
        content = rb.get("content") or ""
        content_trim = content[:4000]  # trim to keep prompt size under control
        rb_summaries.append(
            f"RUNBOOK_ID: {rb.get('id')}\n"
            f"TITLE: {rb.get('title')}\n"
            f"CONTENT:\n{content_trim}\n"
            f"---\n"
        )

    runbooks_blob = "\n".join(rb_summaries) if rb_summaries else "NO RUNBOOKS PROVIDED"

    return (
        "You are an operations assistant. You will be given:\n"
        "1) An alert-like message (raw JSON/text)\n"
        "2) A set of runbooks (unstructured markdown; formats may vary)\n\n"
        "Your job:\n"
        "- Read the alert carefully.\n"
        "- Read the runbooks carefully.\n"
        "- Choose the SINGLE best matching runbook. If none match, set selected_runbook_id to null.\n"
        "- Convert the chosen runbook into a HUMAN-LIKE ordered plan of steps.\n"
        "- Each step must be atomic (something a human would do before moving on).\n"
        "- Steps must be executable one-by-one.\n\n"
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
        "Rules:\n"
        "- Do NOT call tools.\n"
        "- Do NOT trigger actions directly.\n"
        "- If a field is unknown, use null.\n"
        "- steps must be a non-empty array if selected_runbook_id is not null.\n"
        "- If no runbook matches, steps may be an empty array.\n\n"
        "ALERT RAW MESSAGE:\n"
        f"{raw_message_str}\n\n"
        "RUNBOOKS:\n"
        f"{runbooks_blob}\n"
    )


# --------------------------
# Azure Function App Trigger (accepts str or dict)
# --------------------------

def trigger_function_app(
    function_url: str,
    payload: Union[str, Dict[str, Any]],
    function_key: Optional[str] = None,
    max_attempts: int = 3,
    timeout_secs: int = 20
) -> Tuple[int, str]:
    """
    POST payload to Azure Function App.

    - If 'payload' is dict -> Content-Type: application/json
    - If 'payload' is str  -> Content-Type: text/plain
    - Optionally uses x-functions-key header when URL doesn't include ?code=
    """
    if not function_url:
        raise RuntimeError("Function App URL is missing.")

    if isinstance(payload, dict):
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "runbook-orchestrator/azure-function"
        }
        body_bytes = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        headers = {
            "Content-Type": "text/plain",
            "User-Agent": "runbook-orchestrator/azure-function"
        }
        body_bytes = payload.encode("utf-8")
    else:
        raise TypeError(f"Unsupported payload type: {type(payload)}. Use str or dict.")

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
            body = e.read().decode("utf-8", errors="ignore")
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

            # Retry for connectivity errors
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            raise last_err

    if last_err:
        raise last_err
    raise RuntimeError("Function app trigger failed: unknown error")


# --------------------------
# Step-by-step execution helpers (stateful across calls via request payload)
# --------------------------

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
    Caller re-invokes for the next step using execution_state.
    """
    steps = plan.get("steps") or []
    step_obj = steps[step_index] if step_index < len(steps) else None
    if not step_obj:
        raise RuntimeError(f"Invalid step_index={step_index}, no step found")

    payload = {
        "type": "runbook_step",
        "run_id": run_id,
        "step_index": step_index,
        "step": step_obj,
        "summary": plan.get("summary"),
        "params": plan.get("params", {}),
        "selected_runbook_id": plan.get("selected_runbook_id"),
        "selected_runbook_title": plan.get("selected_runbook_title"),
        # Provide original alert context so the executor can act with full info
        "raw_alert": request_json,
    }

    return trigger_function_app(
        function_url=function_url,
        payload=payload,
        function_key=function_key,
        max_attempts=3,
        timeout_secs=20,
    )


# --------------------------
# Primary entry point
# --------------------------

def run_github_workflow(request_json: Dict[str, Any], input_controller) -> Tuple[Dict[str, Any], int]:
    """
    Human-like execution:
      - On first call: build a plan from alert + runbooks, run step 1, return state
      - On continuation calls: run the next step only, return updated state
    """

    try:
        # treat the entire incoming JSON as the "raw message"
        if not isinstance(request_json, dict) or not request_json:
            logger.error("[RUNBOOK_DEBUG] Invalid request body expected non-empty JSON object.")
            return {"success": False, "error": "Invalid payload expected JSON object"}, 400

        # Function endpoint config
        function_url = FUNCTION_APP_URL
        function_key = None  # not needed if URL already has code=

        # Read continuation state (if any)
        state = _get_execution_state(request_json)

        # --------------------------
        # CONTINUATION CALL PATH
        # --------------------------
        if _is_continuation_call(state):
            run_id = state.get("run_id")
            plan = state.get("plan") or {}
            step_index = int(state.get("next_step_index", 0))

            logger.info(f"[RUNBOOK_DEBUG] Continuation call | run_id={run_id} | next_step_index={step_index}")

            if not _plan_has_more_steps(plan, step_index):
                response = {
                    "success": True,
                    "data": {
                        "proposal": {
                            "plan": plan,
                            "run_id": run_id,
                            "execution_ready": False,
                            "status": "completed",
                            "message": "All steps already executed.",
                        }
                    },
                    "timestamp": _now_iso_utc(),
                }
                return response, 200

            # Execute exactly ONE step
            status, resp_text = _execute_single_step_via_function_app(
                function_url=function_url,
                function_key=function_key,
                run_id=run_id,
                step_index=step_index,
                plan=plan,
                request_json=request_json,
            )

            # Update state for next call
            next_step_index = step_index + 1
            updated_state = {
                "run_id": run_id,
                "plan": plan,
                "next_step_index": next_step_index,
                "last_step_status": status,
                "last_step_response": resp_text,
            }

            response = {
                "success": True,
                "data": {
                    "proposal": {
                        "plan": plan,
                        "run_id": run_id,
                        "executed_step_index": step_index,
                        "function_app_status": status,
                        "function_app_response": resp_text,
                        "execution_state": updated_state,
                        "execution_ready": _plan_has_more_steps(plan, next_step_index),
                        "status": "in_progress" if _plan_has_more_steps(plan, next_step_index) else "completed",
                        "message": "Step executed. Re-invoke with execution_state to run the next step.",
                    }
                },
                "timestamp": _now_iso_utc(),
            }
            return response, 200

        # --------------------------
        # NEW RUN PATH
        # --------------------------
        logger.info("[RUNBOOK_DEBUG] New run starting (no execution_state provided)")

        # Load runbooks from disk
        runbooks = load_runbooks()
        logger.info(f"[RUNBOOK_DEBUG] github_workflow: loaded_runbooks={len(runbooks)}")

        # Build a plan using LLM over alert + runbooks
        raw_str_for_llm = json.dumps(request_json, ensure_ascii=False)
        instruction = build_instruction_for_structured_output(raw_str_for_llm, runbooks)

        llm_payload = {
            "type": "user_message",
            "content": instruction,
            "timestamp": _now_iso_utc(),
            "conversation_id": "",
            "source": "splunk",
        }

        summary_and_params_resp = llm_process_with_retry(
            input_controller=input_controller,
            payload=llm_payload,
            format_type="json",
            source="splunk",
            max_attempts=3,
        )

        processed = summary_and_params_resp.get("processed_content", {})
        content = processed.get("content", {})
        content_dict = force_json_dict(content)

        # Normalize plan object
        plan: Dict[str, Any] = {
            "summary": content_dict.get("summary") or "no summary generated",
            "params": content_dict.get("params") or {"cluster": None, "namespace": None, "service": None},
            "selected_runbook_id": content_dict.get("selected_runbook_id"),
            "selected_runbook_title": content_dict.get("selected_runbook_title"),
            "rationale": content_dict.get("rationale") or "",
            "steps": content_dict.get("steps") or [],
        }

        run_id = _new_run_id()

        logger.info(
            f"[RUNBOOK_DEBUG] Plan created | run_id={run_id} | "
            f"selected_runbook_id={plan.get('selected_runbook_id')} | steps={len(plan.get('steps') or [])}"
        )

        # If no runbook matched (steps empty), return plan only (no execution)
        if not plan.get("selected_runbook_id") or not plan.get("steps"):
            response = {
                "success": True,
                "data": {
                    "proposal": {
                        "plan": plan,
                        "run_id": run_id,
                        "execution_ready": False,
                        "status": "no_match",
                        "message": "No suitable runbook matched. No steps executed.",
                    }
                },
                "timestamp": _now_iso_utc(),
            }
            return response, 200

        # Execute exactly ONE step (step 0)
        status, resp_text = _execute_single_step_via_function_app(
            function_url=function_url,
            function_key=function_key,
            run_id=run_id,
            step_index=0,
            plan=plan,
            request_json=request_json,
        )

        # Return state to continue later (step 1 next)
        updated_state = {
            "run_id": run_id,
            "plan": plan,
            "next_step_index": 1,
            "last_step_status": status,
            "last_step_response": resp_text,
        }

        response = {
            "success": True,
            "data": {
                "proposal": {
                    "plan": plan,
                    "run_id": run_id,
                    "executed_step_index": 0,
                    "function_app_status": status,
                    "function_app_response": resp_text,
                    "execution_state": updated_state,
                    "execution_ready": _plan_has_more_steps(plan, 1),
                    "status": "in_progress" if _plan_has_more_steps(plan, 1) else "completed",
                    "message": "Step 1 executed. Re-invoke with execution_state to run the next step.",
                }
            },
            "timestamp": _now_iso_utc(),
        }
        return response, 200

    except Exception as e:
        logger.error(f"[RUNBOOK_DEBUG] Workflow error: {e}")
        return {"success": False, "error": "Internal server error"}, 500