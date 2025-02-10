import os
import subprocess
import json
from openai import AzureOpenAI
from github import Github

# Azure OpenAI Credentials
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
RESOURCE_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

# GitHub Credentials
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME_SECRET", "")  # Ensure REPO_NAME is not None  # Ensure REPO_NAME is not None  # Format: 'username/repository'
BRANCH_NAME = "autoheal-fix"

def get_terraform_error():
    """Reads Terraform apply error from the GitHub Actions log file."""
    log_path = "terraform/tf_error_log.txt"
    try:
        with open(log_path, "r") as log_file:
            error_log = log_file.read().strip()
        
        if error_log and "Error" in error_log:
            return error_log
        else:
            return "No error detected"
    except Exception as e:
        return str(e)

def get_openai_fix(error_message):
    """Send Terraform error to Azure OpenAI and get the fix."""
    client = AzureOpenAI(
        api_version=API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY
    )
    response = client.chat.completions.create(
        model=RESOURCE_NAME,
        messages=[
            {"role": "system", "content": "You are an expert in Terraform troubleshooting."},
            {"role": "user", "content": f"Fix this Terraform error: {error_message}"}
        ]
    )
    return response.choices[0].message.content.strip()

def update_main_tf(fixed_code):
    """Update the main.tf file with the AI-generated fix."""
    tf_path = "terraform/main.tf"
    with open(tf_path, "w") as file:
        file.write(fixed_code)

def create_github_pr():
    """Create a new Git branch, commit the fix, and open a PR."""
    g = Github(GITHUB_TOKEN)
    if not REPO_NAME:
        print("Error: GITHUB_REPO environment variable is missing. Ensure it is set in GitHub Actions secrets.")
        return
        raise ValueError("GITHUB_REPO environment variable is not set correctly.")
    repo = g.get_repo(REPO_NAME)
    
    # Create a new branch
    main_ref = repo.get_git_ref("heads/main")
    repo.create_git_ref(ref=f"refs/heads/{BRANCH_NAME}", sha=main_ref.object.sha)
    
    # Commit changes
    file_path = "terraform/main.tf"
    with open(f"../{file_path}", "r") as file:
        content = file.read()
    repo.get_contents(file_path, ref=BRANCH_NAME)
    repo.update_file(file_path, "AutoHeal: Fix Terraform error", content, repo.get_contents(file_path).sha, branch=BRANCH_NAME)
    
    # Create PR
    repo.create_pull(title="AutoHeal: Fix Terraform Deployment Error", body="Fixes applied using Azure OpenAI.", head=BRANCH_NAME, base="main")

def main():
    """Main execution flow."""
    error_log = get_terraform_error()
    if error_log != "No error detected":
        print(f"Terraform error detected:\n{error_log}")
        fix = get_openai_fix(error_log)
        update_main_tf(fix)
        create_github_pr()
    else:
        print("No Terraform errors detected.")

if __name__ == "__main__":
    main()
