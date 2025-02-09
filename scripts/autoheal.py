import os
import openai

# Get OpenAI credentials from environment variables
OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# Configure OpenAI API
openai.api_key = OPENAI_API_KEY
openai.api_base = OPENAI_ENDPOINT

# Define correct log file path (inside terraform directory)
error_log_path = os.path.join(os.getcwd(), "terraform/tf_error_log.txt")

# Check if the error log file exists
if not os.path.exists(error_log_path):
    print(f"Error log {error_log_path} not found in {os.getcwd()}. Exiting auto-heal process.")
    exit(1)

# Read the error log
with open(error_log_path, "r") as f:
    error_log = f.read()

print("Sending error logs to OpenAI for analysis...")

try:
    # Send error log to OpenAI for analysis using the new API format
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an AI that analyzes CI/CD deployment errors and suggests code fixes."},
            {"role": "user", "content": f"Analyze this Terraform deployment error and suggest a fix:\n\n{error_log}"}
        ],
        temperature=0
    )

    # Extract AI-suggested fix
    fix_suggestion = response["choices"][0]["message"]["content"]

    # Save fix suggestion for later processing
    with open("ai_fix_suggestion.txt", "w") as f:
        f.write(fix_suggestion)

    print("AI analysis complete. Fix suggestion saved.")
except Exception as e:
    print(f"Error occurred while calling OpenAI API: {e}")
    exit(1)
