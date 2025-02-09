import os
from openai import AzureOpenAI

API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
RESOURCE_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")


client = AzureOpenAI(
    api_version=API_VERSION,
    azure_endpoint=AZURE_ENDPOINT,
    api_key=API_KEY
)

completion = client.chat.completions.create(
    model=RESOURCE_NAME,
    messages=[
        {   
            "role": "user",
            "content": "How do I output all files in a directory using Python?",
        },  
    ],  
)
print(completion.to_json())
