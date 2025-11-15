from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import logging

import logging
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient

logger = logging.getLogger(__name__)

def migrate_prompts(
    client: MongoClient,
    test_id: str,
    prompt_names: list = ["base_prompt", "meta_prompt", "eval_parameters"]
):
    """
    Migrate specific prompt fields from 'runs' collection (source)
    to 'prompts' collection (target), filtered by test_id.
    """
    source_db = client["client-poc"]
    target_db = client["poc-llm-processor"]

    runs_collection = source_db["runs"]
    prompt_collection = target_db["prompts"]

    runs_doc = runs_collection.find_one({"test_id": test_id})
    if not runs_doc:
        logger.warning(f"⚠️ No run found for test_id={test_id}")
        return {}


    for name in prompt_names:
        prompt_text = runs_doc.get(name)
        if not prompt_text:
            continue

        target_doc = {
            "_id": ObjectId(),
            "name": name,
            "version": test_id,
            "status": "active",
            "type": "system",
            "prompt": prompt_text,
            "_metadata": {
                "source_run_id": str(runs_doc.get("_id")),
                "created_at": datetime.now().isoformat()
            }
        }

        prompt_collection.insert_one(target_doc)
        logger.info(f"✅ Migrated prompt '{name}' for test_id= {test_id}")




def update_prompt(
    client: MongoClient,
    prompt_text: str,
    version: str,
    prompt_name: str,
    prompt_type: str = "system"
):
    """
    Insert or update a prompt document in 'prompts' collection.
    """
    target_db = client["poc-llm-processor"]
    prompt_collection = target_db["prompts"]

    now = datetime.now().isoformat()

    query = {"name": prompt_name, "version": version, "type": prompt_type}

    update_doc = {
        "$set": {
            "prompt": prompt_text,
            "status": "active",
            "_metadata.updated_at": now
        },
        "$setOnInsert": {
            "_id": ObjectId(),
            "_metadata.created_at": now
        }
    }

    result = prompt_collection.update_one(query, update_doc, upsert=True)

    if result.matched_count > 0:
        logger.info(f"🛠️ Updated existing prompt '{prompt_name}' (version={version})")
    else:
        logger.info(f"✨ Created new prompt '{prompt_name}' (version={version})")

    # Retourner le document à jour
    return prompt_collection.find_one(query)


def find_prompt(client: MongoClient, name: str, version: str, prompt_type: str = "system"):
    """
    Retrieve a specific prompt document by name, version, and type.
    """
    db = client["poc-llm-processor"]
    prompt_collection = db["prompt"]

    query = {"name": name, "version": version, "type": prompt_type}
    prompt_doc = prompt_collection.find_one(query)

    if prompt_doc:
        logger.info(f"🔍 Found prompt '{name}' (version={version})")
    else:
        logger.warning(f"❌ Prompt '{name}' (version={version}) not found.")

    return prompt_doc
