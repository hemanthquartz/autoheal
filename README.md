import logging
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.mgmt.cosmosdb import CosmosDBManagementClient
from azure.cosmos import CosmosClient, PartitionKey

# keep your constants
EMBEDDING_DIM = 1536

def ensure_cosmos_once():
    global _cosmos_ready, _cosmos_container

    if _cosmos_ready:
        return _cosmos_container

    subscription_id = "5204df69-30ab-4345-a9d2-ddb0ac139a3c"
    rg_name = "pde-azure-cicd-ai-poc"
    location = "eastus"
    account_name = "runbooks-automation"               # already exists
    db_name = "runbooks-automation-db"
    container_name = "runbooks-automation-container"

    cred = DefaultAzureCredential()
    cmc = CosmosDBManagementClient(cred, subscription_id)

    # 1) Verify Cosmos account exists (no create)
    try:
        acct = cmc.database_accounts.get(rg_name, account_name)
        logging.info("Cosmos account found: %s", account_name)
    except ResourceNotFoundError:
        raise Exception(
            f"Cosmos account '{account_name}' not found in RG '{rg_name}'. "
            "Fix account_name/rg_name or create it outside this function."
        )
    except HttpResponseError as e:
        # This is usually RBAC related (403), you want to SEE it clearly
        raise Exception(f"Failed to read Cosmos account (RBAC?). Details: {e}")

    # 2) Get endpoint + keys (keys require RBAC: listKeys)
    try:
        keys = cmc.database_accounts.list_keys(rg_name, account_name)
        key = keys.primary_master_key
    except HttpResponseError as e:
        raise Exception(
            "Failed to list Cosmos keys. Your Function App Managed Identity likely "
            "does NOT have permission to listKeys. Assign 'Contributor' (or "
            "'Cosmos DB Account Contributor') on the Cosmos account or RG. "
            f"Details: {e}"
        )

    endpoint = acct.document_endpoint or f"https://{account_name}.documents.azure.com:443/"

    # 3) Create DB + container if missing
    client = CosmosClient(endpoint, credential=key)
    database = client.create_database_if_not_exists(id=db_name)

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