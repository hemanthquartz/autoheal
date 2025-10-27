import os, json, urllib.request, urllib.error
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    # read config from app settings
    token = os.getenv("GITHUB_TOKEN", "")
    owner = os.getenv("GITHUB_OWNER", "")
    repo  = os.getenv("GITHUB_REPO", "")
    if not (token and owner and repo):
        return func.HttpResponse("Missing GITHUB_* settings", status_code=500)

    # read caller body (optional)
    try:
        b = req.get_json()
    except Exception:
        b = {}

    payload = {
        "event_type": b.get("event_type", "splunk_alert"),
        "client_payload": b.get("client_payload", b)
    }

    # call GitHub
    url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "azure-fn"
    }
    req_ = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req_, timeout=10).close()   # 204 on success
        return func.HttpResponse(status_code=204)
    except urllib.error.HTTPError as e:
        return func.HttpResponse(e.read().decode() or str(e), status_code=e.code)
    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)