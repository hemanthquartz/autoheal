import os
import requests

# Get OpenAI credentials from environment variables
OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
OPENAI_RESOURCE_NAME = os.getenv("AZURE_OPENAI_RESOURCE_NAME")  # e.g., "openaiaccount9962b28a"
OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-12-01-preview")

# Construct the correct API endpoint (must match working cURL)
API_URL = f"https://{OPENAI_RESOURCE_NAME}.openai.azure.com/openai/deployments/{OPENAI_DEPLOYMENT_NAME}/chat/completions?api-version={OPENAI_API_VERSION}"

print(f"Using OpenAI API Endpoint: {API_URL}")

# Check API key
if not OPENAI_API_KEY:
    print("Error: OpenAI API key is missing. Exiting auto-heal process.")
    exit(1)

# Define correct log file path
error_log_path = os.path.join(os.getcwd(), "terraform/tf_error_log.txt")

# Check if the error log file exists
if not os.path.exists(error_log_path):
    print(f"Error log {error_log_path} not found in {os.getcwd()}. Exiting auto-heal process.")
    exit(1)

# Read the error log
with open(error_log_path, "r") as f:
    error_log = f.read()

print("Testing network connectivity to OpenAI API...")

try:
    # Verify network connectivity
    response = requests.get(API_URL, headers={"api-key": OPENAI_API_KEY}, timeout=10)
    print(f"API Connectivity Test Response Code: {response.status_code}")
    if response.status_code == 404:
        print(f"❌ ERROR: API returned 404. The OpenAI deployment '{OPENAI_DEPLOYMENT_NAME}' might not exist.")
        exit(1)
except requests.RequestException as e:
    print(f"Network error while connecting to OpenAI: {e}")
    exit(1)

print("Sending error logs to OpenAI for analysis...")

# Define the request payload
payload = {
    "messages": [
        {"role": "system", "content": "You are an AI that analyzes CI/CD deployment errors and suggests code fixes."},
        {"role": "user", "content": f"Analyze this Terraform deployment error and suggest a fix:\n\n{error_log}"}
    ]
}

headers = {
    "Content-Type": "application/json",
    "api-key": OPENAI_API_KEY
}

try:
    response = requests.post(API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"❌ ERROR: OpenAI API responded with {response.status_code} - {response.text}")
        exit(1)

    fix_suggestion = response.json()["choices"][0]["message"]["content"]

    # Save fix suggestion for later processing
    with open("ai_fix_suggestion.txt", "w") as f:
        f.write(fix_suggestion)

    print("✅ AI analysis complete. Fix suggestion saved.")
except Exception as e:
    print(f"Error occurred while calling OpenAI API: {e}")
    exit(1)
