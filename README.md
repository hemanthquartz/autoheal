# Restart Windows Service on Azure VM

Keywords: restart, windows, service, vm, azure, win_services, telegraf

## When to use
Use when a Splunk/SignalFx alert indicates a Windows service is unhealthy on an Azure VM.

## Required parameters (from alert dimensions)
- azure_resource_id (full Azure resource ID of the VM)
- service_name (Windows Service name, e.g., AppReadiness)

## Action
Restart the service using Azure VM Run Command (PowerShell).

## Validation
- Service status becomes Running.
- Alert clears (or downstream health check recovers).


import re

def parse_dimensions_kv(dimensions: str) -> dict:
    """
    Parse a SignalFx-style 'dimensions' string:
    "{k=v, a=b, ...}" into dict. Splits on commas, then first '='.
    """
    if not dimensions:
        return {}

    s = dimensions.strip()

    # Strip wrapping braces if present
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



def match_runbooks(alert_summary, params, runbooks):
    """
    Deterministic matching: keyword scoring against summary + ALL param values.
    """
    haystack_parts = [alert_summary or ""]
    if isinstance(params, dict):
        for v in params.values():
            if v is None:
                continue
            haystack_parts.append(str(v))
    text_l = " ".join(haystack_parts).lower()

    ranked = []
    for rb in runbooks:
        score = 0
        for kw in rb.get("keywords", []):
            if kw.lower() in text_l:
                score += 1
        ranked.append((score, rb))

    ranked.sort(key=lambda x: x[0], reverse=True)
    filtered = [rb for score, rb in ranked if score > 0] or ([ranked[0][1]] if ranked else [])
    return filtered[:3]



import os, json, urllib.request, urllib.error

def github_repository_dispatch(event_type: str, client_payload: dict):
    token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")

    if not (token and owner and repo):
        raise RuntimeError("Missing GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO in app settings.")

    url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "runbook-orchestrator"
    }

    payload = {"event_type": event_type, "client_payload": client_payload}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            # GitHub often returns 204 for dispatch
            return resp.status
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub dispatch failed: {e.code} {e.read().decode('utf-8', errors='ignore')}")



@api_bp.route("/github_workflow", methods=["POST"])
def github_workflow():
    try:
        data = request.get_json(silent=True) or {}
        alert_raw = data.get("dimensions")
        if not alert_raw:
            return jsonify({"success": False, "error": "Alert payload missing"}), 400

        # 0) Parse dimensions deterministically
        dims = parse_dimensions_kv(alert_raw)

        # 1) LLM summary (keep your existing approach)
        input_controller = current_app.input_controller
        instruction = build_instruction_for_structured_output(alert_raw)

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
            max_attempts=3
        )

        processed = summary_and_params_resp.get("processed_content", {})
        content = processed.get("content", {})
        content_dict = _force_json_dict(content)

        alert_summary = content_dict.get("summary") or "No summary generated"

        # 2) Build params (deterministic first; LLM params optional)
        llm_params = content_dict.get("params") or {}
        extracted_params = {
            # Your old fields (keep them)
            "cluster": llm_params.get("cluster"),
            "namespace": llm_params.get("namespace"),
            "service": llm_params.get("service") or dims.get("service.name") or dims.get("service"),
            # New fields for Windows/Azure service restart
            "os_type": dims.get("os.type"),
            "service_name": dims.get("service.name") or llm_params.get("service"),
            "azure_resource_id": dims.get("azure_resource_id"),
            "azure_resource_group": dims.get("azure.resourcegroup.name"),
            "azure_vm_name": dims.get("azure.vm.name"),
            "host_name": dims.get("host.name"),
            "cloud_region": dims.get("cloud.region"),
        }

        # Clean up empty strings
        for k in list(extracted_params.keys()):
            if extracted_params[k] == "":
                extracted_params[k] = None

        # 3) Load + match runbooks
        runbooks = load_runbooks()
        matched = match_runbooks(
            alert_summary=alert_summary,
            params=extracted_params,
            runbooks=runbooks
        )

        suggested_runbooks = [
            {"id": rb["id"], "title": rb["title"], "content": rb["content"]}
            for rb in matched
        ] if matched else []

        selected_runbook = suggested_runbooks[0] if suggested_runbooks else None
        action = selected_runbook["title"] if selected_runbook else None

        proposal = {
            "summary": alert_summary,
            "params": extracted_params,
            "suggested_runbooks": suggested_runbooks,
            "selected_runbook": selected_runbook,
            "action": action,
            "execution_ready": bool(selected_runbook),
        }

        # 4) Execute now (no approval yet)
        if selected_runbook:
            event_type = selected_runbook["id"]  # stable mapping: runbook id = GitHub dispatch event_type
            client_payload = {
                "proposal": proposal,
                "dimensions_raw": alert_raw,
            }
            status = github_repository_dispatch(event_type=event_type, client_payload=client_payload)
            proposal["github_dispatch_status"] = status

        return jsonify({
            "success": True,
            "data": {"proposal": proposal},
            "timestamp": _now_iso_utc()
        }), 200

    except Exception as e:
        logger.error(f"WorkFlow error: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


