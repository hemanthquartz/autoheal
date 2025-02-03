
import os
import sys
import openai
from github import Github

# Azure OpenAI Configuration
openai.api_type = "azure"
openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.api_version = "2023-05-15"

# GitHub Configuration
github_token = os.getenv("GITHUB_TOKEN")
repo_name = os.getenv("GITHUB_REPOSITORY")
g = Github(github_token)
repo = g.get_repo(repo_name)

# Deployment Error
error_message = sys.argv[1]

# Step 1: Analyze Error with Azure OpenAI
response = openai.ChatCompletion.create(
    engine="gpt-4",
    messages=[
        {"role": "system", "content": "You are an expert DevOps engineer."},
        {"role": "user", "content": f"Analyze this Terraform deployment error and suggest a code fix:\n\n{error_message}"}
    ],
    temperature=0
)

suggested_fix = response['choices'][0]['message']['content']

# Step 2: Apply Fix (simple example: update a file with suggested fix)
fix_branch = "autoheal-fix-branch"
base_branch = "main"
file_to_fix = "terraform/main.tf"

# Get the current content
contents = repo.get_contents(file_to_fix, ref=base_branch)
new_content = contents.decoded_content.decode() + f"\n# Auto-Heal Fix:\n# {suggested_fix}"

# Step 3: Create a New Branch
source = repo.get_branch(base_branch)
repo.create_git_ref(ref=f"refs/heads/{fix_branch}", sha=source.commit.sha)

# Step 4: Commit the Fix
repo.update_file(
    path=file_to_fix,
    message="Auto-Heal: Fix for deployment error",
    content=new_content,
    sha=contents.sha,
    branch=fix_branch
)

# Step 5: Create a Pull Request
repo.create_pull(
    title="Auto-Heal: Fix for Deployment Error",
    body=f"### Suggested Fix:\n{suggested_fix}",
    head=fix_branch,
    base=base_branch
)
