from flask import Flask, request, jsonify, current_app
from datetime import datetime
import os
import logging

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.cosmosdb import CosmosDBManagementClient
from azure.mgmt.cosmosdb.models import (
    DatabaseAccountCreateUpdateParameters,
    Location,
)
from azure.cosmos import CosmosClient, PartitionKey

from langchain.text_splitters import RecursiveCharacterTextSplitter

# ------------------------------------------------------------------------------
# App & Logging
# ------------------------------------------------------------------------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Global Cosmos bootstrap state
# ------------------------------------------------------------------------------

_cosmos_ready = False
_cosmos_container = None
EMBEDDING_DIM = 1536  # must match input_controller embeddings

# ------------------------------------------------------------------------------
# COSMOS PROVISIONING
# ------------------------------------------------------------------------------

def ensure_cosmos_once():
    """
    Creates if not exists:
    - Resource Group
    - Cosmos DB account
    - Database
    - Container with vector indexing
    """
    global _cosmos_ready, _cosmos_container

    if _cosmos_ready:
        return _cosmos_container

    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    rg_name = os.getenv("AZURE_RESOURCE_GROUP")
    location = os.getenv("AZURE_LOCATION", "eastus")
    account_name = os.getenv("COSMOS_ACCOUNT_NAME")
    db_name = os.getenv("COSMOS_DB_NAME", "runbooksdb")
    container_name = os.getenv("COSMOS_CONTAINER", "runbook_chunks")

    cred = DefaultAzureCredential()

    # Create or update resource group
    rmc = ResourceManagementClient(cred, subscription_id)
    rmc.resource_groups.create_or_update(
        rg_name,
        {"location": location}
    )

    # Create Cosmos DB account if missing
    cmc = CosmosDBManagementClient(cred, subscription_id)
    try:
        cmc.database_accounts.get(rg_name, account_name)
    except Exception:
        params = DatabaseAccountCreateUpdateParameters(
            location=location,
            locations=[Location(location_name=location, failover_priority=0)],
            kind="GlobalDocumentDB",
            database_account_offer_type="Standard",
            public_network_access="Enabled",
        )
        poller = cmc.database_accounts.begin_create_or_update(
            rg_name, account_name, params
        )
        poller.result()

    # Retrieve keys
    keys = cmc.database_accounts.list_keys(rg_name, account_name)
    endpoint = f"https://{account_name}.documents.azure.com:443/"
    key = keys.primary_master_key

    # Create client and database
    client = CosmosClient(endpoint, key)
    database = client.create_database_if_not_exists(id=db_name)

    # Vector index policy
    indexing_policy = {
        "indexingMode": "consistent",
        "includedPaths": [{"path": "/*"}],
        "vectorIndexes": [
            {
                "path": "/embedding",
                "kind": "flat",
                "dataType": "float32",
                "dimensions": EMBEDDING_DIM,
            }
        ],
    }

    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=PartitionKey(path="/runbook"),
        indexing_policy=indexing_policy,
        offer_throughput=400,
    )

    _cosmos_ready = True
    _cosmos_container = container
    return container

# ------------------------------------------------------------------------------
# RUNBOOK INDEXING
# ------------------------------------------------------------------------------

def index_runbooks(container, input_controller):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100
    )
    runbook_dir = "./runbooks"
    if not os.path.isdir(runbook_dir):
        return 0

    total = 0
    for fname in os.listdir(runbook_dir):
        if not fname.endswith(".md"):
            continue

        with open(os.path.join(runbook_dir, fname), "r", encoding="utf-8") as f:
            content = f.read()

        chunks = splitter.split_text(content)

        for i, chunk in enumerate(chunks):
            emb_resp = input_controller.process(
                data={
                    "type": "embedding_request",
                    "content": chunk,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                format_type="json",
                source="web_ui",
            )

            vec = emb_resp.get("processed_content", {}).get("embedding")
            if not vec:
                continue

            doc = {
                "id": f"{fname}-{i}",
                "runbook": fname,
                "content": chunk,
                "embedding": vec,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
            container.upsert_item(doc)
            total += 1

    return total

# ------------------------------------------------------------------------------
# VECTOR SEARCH
# ------------------------------------------------------------------------------

def search_runbooks(container, query_text, input_controller, k=3):
    emb_resp = input_controller.process(
        data={
            "type": "embedding_request",
            "content": query_text,
            "timestamp": datetime.utcnow().isoformat(),
        },
        format_type="json",
        source="web_ui",
    )
    query_vec = emb_resp.get("processed_content", {}).get("embedding")
    if not query_vec:
        return []

    query = """
    SELECT TOP @k
      c.id, c.runbook, c.content,
      VectorDistance(c.embedding, @embedding) AS distance
    FROM c
    ORDER BY distance
    """
    params = [
        {"name": "@k", "value": k},
        {"name": "@embedding", "value": query_vec},
    ]

    return list(
        container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        )
    )

# ------------------------------------------------------------------------------
# MAIN WORKFLOW
# ------------------------------------------------------------------------------

@app.route("/github-workflow", methods=["POST"])
def github_workflow():
    try:
        data = request.get_json()
        alert_raw = data.get("dimensions")
        if not alert_raw:
            return jsonify({"success": False, "error": "Alert missing"}), 400

        input_controller = current_app.input_controller

        container = ensure_cosmos_once()
        if not _cosmos_ready:
            index_runbooks(container, input_controller)

        summary_resp = input_controller.process(
            data={
                "type": "user_message",
                "content": f"Summarize this Splunk alert:\n{alert_raw}",
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="splunk",
        )
        summary_text = summary_resp.get("processed_content", {}).get("content", "No summary")

        param_resp = input_controller.process(
            data={
                "type": "user_message",
                "content": f"Extract Cluster ID, Namespace, Service from:\n{alert_raw}",
                "timestamp": datetime.utcnow().isoformat(),
            },
            format_type="json",
            source="splunk",
        )
        params = param_resp.get("processed_content", {}).get("content", "{}")

        hits = search_runbooks(container, summary_text, input_controller)

        proposal = {
            "summary": summary_text,
            "params": params,
            "suggested_runbooks": [h["content"] for h in hits],
            "action": "Restart Service via GitHub Action",
        }
        return jsonify({"success": True, "data": {"proposal": proposal}}), 200

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return jsonify({"success": False, "error": "Internal"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)