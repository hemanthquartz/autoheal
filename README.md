import os
import json
import logging
import openai
import azure.functions as func

# Load OpenAI credentials from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
OPENAI_DEPLOYMENT = os.getenv("OPENAI_DEPLOYMENT")

openai.api_type = "azure"
openai.api_key = OPENAI_API_KEY
openai.api_base = OPENAI_ENDPOINT
openai.api_version = "2023-03-15-preview"  # Use the correct API version

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing OpenAI request.")

    try:
        req_body = req.get_json()
        prompt = req_body.get("prompt")

        if not prompt:
            return func.HttpResponse("Please provide a prompt", status_code=400)

        # Call OpenAI API
        response = openai.ChatCompletion.create(
            engine=OPENAI_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )

        return func.HttpResponse(json.dumps(response), mimetype="application/json")

    except Exception as e:
        logging.error(str(e))
        return func.HttpResponse(str(e), status_code=500)
