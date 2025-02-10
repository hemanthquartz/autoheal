# Define the corrected autoheal.py script
import os
from openai import AzureOpenAI

API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
RESOURCE_NAME = os.getenv("AZURE_OPENAI_RESOURCE_NAME")

client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=AZURE_ENDPOINT,
    api_key=API_KEY
)

# Corrected file path
ERROR_LOG_PATH = "tf_error_log.txt"  # Fixed incorrect path reference

def get_openai_fix(error_log):
    completion = client.chat.completions.create(
        model=RESOURCE_NAME,
        messages=[
            {
                "role": "user",
                "content": f"Analyze this Terraform deployment error and suggest a fix:\n\n{error_log}",
            },
        ],
    )

    # Fixed response handling (accessing `.content` instead of `["content"]`)
    return completion.choices[0].message.content.strip()

def main():
    if not os.path.exists(ERROR_LOG_PATH):
        print(f"Error: Terraform error log file '{ERROR_LOG_PATH}' not found.")
        return

    with open(ERROR_LOG_PATH, "r") as f:
        error_log = f.read()

    print("Terraform error detected, analyzing with Azure OpenAI...")
    fix = get_openai_fix(error_log)

    print("\n=== AI-Suggested Fix ===")
    print(fix)

    # Save fix suggestion for later processing
    with open("ai_fix_suggestion.txt", "w") as f:
        f.write(fix)

if __name__ == "__main__":
    main()
