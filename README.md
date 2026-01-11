from flask import Flask, request, jsonify, current_app
from datetime import datetime
import os
import logging

from langchain.text_splitters import RecursiveCharacterTextSplitter

# ------------------------------------------------------------------------------
# App & Logging
# ------------------------------------------------------------------------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# RUNBOOK LOADING (FILE SYSTEM BASED)
# ------------------------------------------------------------------------------

def load_runbooks():
    """
    Reads all markdown files from ./runbooks directory
    Returns list of runbook documents
    """
    runbooks = []
    runbook_dir = os.path.join(os.path.dirname(__file__), "runbooks")

    if not os.path.isdir(runbook_dir):
        logger.warning("Runbooks directory not found")
        return runbooks

    for fname in os.listdir(runbook_dir):
        if not fname.endswith(".md"):
            continue

        path = os.path.join(runbook_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        runbooks.append({
            "name": fname,
            "content": content
        })

    return runbooks


# ------------------------------------------------------------------------------
# SEMANTIC MATCHING (NO VECTOR DB)
# ------------------------------------------------------------------------------

def match_runbooks(alert_summary, runbooks, input_controller, top_k=3):
    """
    Uses AI reasoning (via input_controller) to select
    the most relevant runbooks
    """
    matches = []

    for rb in runbooks:
        prompt = f"""
You are an SRE assistant.

Alert summary:
{alert_summary}

Runbook:
{rb['content']}

Rate relevance from 0 to 1.
Return ONLY the numeric score.
"""
        score_resp = input_controller.process(
            data={
                "type": "user_message",
                "content": prompt,
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="web_ui",
        )

        raw_score = score_resp.get("processed_content", {}).get("content", "0")

        try:
            score = float(raw_score.strip())
        except Exception:
            score = 0.0

        matches.append({
            "runbook": rb["name"],
            "content": rb["content"],
            "score": score
        })

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:top_k]


# ------------------------------------------------------------------------------
# MAIN WORKFLOW
# ------------------------------------------------------------------------------

@app.route("/github-workflow", methods=["POST"])
def github_workflow():
    try:
        # -----------------------------
        # INPUT
        # -----------------------------
        data = request.get_json()
        alert_raw = data.get("dimensions")

        if not alert_raw:
            return jsonify({
                "success": False,
                "error": "Alert payload missing"
            }), 400

        input_controller = current_app.input_controller

        # -----------------------------
        # 1. SUMMARIZE ALERT
        # -----------------------------
        summary_resp = input_controller.process(
            data={
                "type": "user_message",
                "content": f"Summarize this Splunk alert:\n{alert_raw}",
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="splunk",
        )

        alert_summary = summary_resp.get(
            "processed_content", {}
        ).get("content", "No summary generated")

        # -----------------------------
        # 2. EXTRACT PARAMETERS
        # -----------------------------
        param_resp = input_controller.process(
            data={
                "type": "user_message",
                "content": f"""
Extract the following if present and return JSON only:
- cluster
- namespace
- service
From this alert:
{alert_raw}
""",
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="splunk",
        )

        extracted_params = param_resp.get(
            "processed_content", {}
        ).get("content", "{}")

        # -----------------------------
        # 3. LOAD RUNBOOKS (LOCAL)
        # -----------------------------
        runbooks = load_runbooks()

        # -----------------------------
        # 4. MATCH RUNBOOKS
        # -----------------------------
        matched_runbooks = match_runbooks(
            alert_summary,
            runbooks,
            input_controller
        )

        # -----------------------------
        # 5. BUILD PROPOSAL
        # -----------------------------
        proposal = {
            "summary": alert_summary,
            "params": extracted_params,
            "suggested_runbooks": [
                rb["content"] for rb in matched_runbooks
            ],
            "action": "Restart Service via GitHub Action",
        }

        return jsonify({
            "success": True,
            "data": {
                "proposal": proposal
            }
        }), 200

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


# ------------------------------------------------------------------------------
# APP START
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)