from flask import Flask, request, jsonify, current_app
from datetime import datetime
import os
import logging

# ------------------------------------------------------------------------------
# App & Logging
# ------------------------------------------------------------------------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# RUNBOOK LOADING (PURE PYTHON)
# ------------------------------------------------------------------------------

def load_runbooks():
    """
    Load all runbooks from ./runbooks folder
    No AI, no external libraries
    """
    runbooks = []
    base_dir = os.path.dirname(__file__)
    runbook_dir = os.path.join(base_dir, "runbooks")

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
# RUNBOOK MATCHING (AI VIA INPUT_CONTROLLER ONLY)
# ------------------------------------------------------------------------------

def match_runbooks(alert_summary, runbooks, input_controller, top_k=3):
    """
    Uses input_controller to evaluate relevance.
    No embeddings, no vectors, no LangChain.
    """
    scored = []

    for rb in runbooks:
        prompt = (
            "You are an SRE assistant.\n\n"
            f"Alert summary:\n{alert_summary}\n\n"
            f"Runbook:\n{rb['content']}\n\n"
            "Score relevance from 0 to 1.\n"
            "Return ONLY the numeric score."
        )

        resp = input_controller.process(
            data={
                "type": "user_message",
                "content": prompt,
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="web_ui",
        )

        raw_score = resp.get("processed_content", {}).get("content", "0")

        try:
            score = float(raw_score.strip())
        except Exception:
            score = 0.0

        scored.append({
            "runbook": rb["name"],
            "content": rb["content"],
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


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
                "content": (
                    "Extract cluster, namespace, and service as JSON.\n\n"
                    f"Alert:\n{alert_raw}"
                ),
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="splunk",
        )

        extracted_params = param_resp.get(
            "processed_content", {}
        ).get("content", "{}")

        # -----------------------------
        # 3. LOAD RUNBOOKS
        # -----------------------------
        runbooks = load_runbooks()

        # -----------------------------
        # 4. MATCH RUNBOOKS
        # -----------------------------
        matched = match_runbooks(
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
            "suggested_runbooks": [rb["content"] for rb in matched],
            "action": "Restart Service via GitHub Action",
        }

        return jsonify({
            "success": True,
            "data": {"proposal": proposal}
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