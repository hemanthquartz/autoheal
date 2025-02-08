
import os
import openai

# Get OpenAI credentials from environment variables
OPENAI_KEY = os.getenv("OPENAI_KEY")

# Configure OpenAI API
openai.api_key = OPENAI_KEY

# Read the error log
with open("error_log.txt", "r") as f:
    error_log = f.read()

# Send error log to OpenAI for analysis using the new API format
response = openai.ChatCompletion.create(
    model="gpt-4",  # Corrected API usage
    messages=[
        {"role": "system", "content": "You are an AI that analyzes CI/CD deployment errors and suggests code fixes."},
        {"role": "user", "content": f"Analyze this deployment error and suggest a fix:\n\n{error_log}"}
    ],
    temperature=0
)

# Extract AI-suggested fix
fix_suggestion = response["choices"][0]["message"]["content"]

# Save fix suggestion for later processing
with open("ai_fix_suggestion.txt", "w") as f:
    f.write(fix_suggestion)

print("AI analysis complete. Fix suggestion saved.")
