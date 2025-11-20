from pymongo import MongoClient, ReturnDocument
from bson import ObjectId
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def write_run(test_id: str, run_id: str, data: dict, client):
    """
    Insert or update a nested iteration inside a specific run.
    
    In the 'runs' collection.
    - If test_id exists and run exists → push new iteration in
      runs.$[elem].iterations
    - If test_id exists but run doesn't → append a new run object
    - If test_id doesn't exist → create full document
    """
    db = client["client-poc"]
    collection = db["runs"]
    now = datetime.now()

    # Vérifie si le document du test existe
    test_doc = collection.find_one({"test_id": test_id})

    if not test_doc:
        # Cas 1: Aucun document pour ce test_id → on le crée
        new_doc = {
            "_id": ObjectId(),
            "test_id": test_id,
            "runs": [
                {
                    "run": run_id,
                    "iterations": [data]
                }
            ],
            "created_at": now,
            "updated_at": now,
        }
        collection.insert_one(new_doc)
        logger.info(f"✨ Created new test document with run {run_id}")
        return new_doc

    # Vérifie si le run existe déjà
    run_exists = any(
        r.get("run") == run_id for r in test_doc.get("runs", [])
    )

    if run_exists:
        # Cas 2: Le run existe → on push une nouvelle itération
        result = collection.update_one(
            {"test_id": test_id},
            {
                "$push": {"runs.$[elem].iterations": data},
                "$set": {"updated_at": now},
            },
            array_filters=[{"elem.run": run_id}],
        )
        logger.info(
            f"🧩 Added new iteration to existing run '{run_id}' "
            f"(test_id={test_id})"
        )
        return result

    else:
        # Cas 3: Le run n'existe pas encore → on l'ajoute au tableau "runs"
        new_run = {
            "run": run_id,
            "iterations": [data]
        }
        result = collection.update_one(
            {"test_id": test_id},
            {
                "$push": {"runs": new_run},
                "$set": {"updated_at": now},
            }
        )
        logger.info(f"➕ Added new run '{run_id}' to test_id={test_id}")
        return result


def read_output_queue_operations(client: MongoClient):
    """
    Reads documents from 'jobs' collection.
    
    Where status='PROCESSED' and clientReference.collection='runs'.
    Returns a generator of relevant documents for further processing.
    """
    db = client["poc-llm-processor"]
    collection = db["jobs"]

    query = {
        "status": "PROCESSED",
        "responseData.status": "ok",
        "clientReference.collection": "runs"
    }

    projection = {
        "_id": 1,
        "responseData": 1,
        "clientReference": 1,
    }

    cursor = collection.find(query, projection)

    results = list(cursor)
    logger.info(
        f"📤 Found {len(results)} processed items in jobs collection "
        f"ready for next step."
    )
    return results
