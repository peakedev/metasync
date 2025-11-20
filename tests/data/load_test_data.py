#!/usr/bin/env python3
"""
Load test data into MongoDB
Clears and repopulates all collections with data from JSON files
"""
import json
import sys
from pathlib import Path
from bson import ObjectId

# Add project root to path to import utilities
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import config
from utilities.cosmos_connector import get_mongo_client, clear_collection, safe_operation


def convert_mongodb_json(data):
    """
    Convert MongoDB extended JSON format to Python objects.
    Handles $oid for ObjectId fields.
    """
    if isinstance(data, dict):
        # Check if this is an ObjectId field
        if "$oid" in data:
            return ObjectId(data["$oid"])
        # Recursively process all dict values
        return {key: convert_mongodb_json(value) for key, value in data.items()}
    elif isinstance(data, list):
        # Recursively process all list items
        return [convert_mongodb_json(item) for item in data]
    else:
        # Return primitive values as-is
        return data


def load_collection_data(mongo_client, db_name: str, collection_name: str, documents: list):
    """
    Load documents into a collection.
    """
    if not documents:
        print(f"📭 No documents to load for '{collection_name}'")
        return {"success": True, "inserted_count": 0}
    
    try:
        print(f"📥 Loading {len(documents)} document(s) into '{collection_name}'...")
        
        db = mongo_client[db_name]
        collection = db[collection_name]
        
        # Convert MongoDB extended JSON format
        converted_documents = convert_mongodb_json(documents)
        
        def insert_operation():
            return collection.insert_many(converted_documents)
        
        result = safe_operation(insert_operation)
        inserted_count = len(result.inserted_ids)
        
        print(f"✅ Inserted {inserted_count} document(s) into '{collection_name}'")
        
        return {
            "success": True,
            "inserted_count": inserted_count
        }
    except Exception as e:
        print(f"❌ Error loading data into '{collection_name}': {e}")
        return {
            "success": False,
            "error": str(e),
            "inserted_count": 0
        }


def load_all_test_data():
    """
    Main function to load all test data from JSON files.
    """
    print("=" * 60)
    print("🚀 Starting test data load process")
    print("=" * 60)
    
    # Get database configuration
    db_connection_string = config.db_connection_string
    db_name = config.db_name
    
    print(f"\n📊 Database: {db_name}")
    
    # Connect to MongoDB
    print(f"🔌 Connecting to MongoDB...")
    mongo_client = get_mongo_client(db_connection_string)
    
    # Get all JSON files in the current directory
    data_dir = Path(__file__).parent
    json_files = sorted(data_dir.glob("*.json"))
    
    if not json_files:
        print("⚠️ No JSON files found in tests/data directory")
        return
    
    print(f"\n📂 Found {len(json_files)} JSON file(s) to process\n")
    
    # Track statistics
    stats = {
        "total_collections": 0,
        "total_documents_cleared": 0,
        "total_documents_inserted": 0,
        "failed_collections": []
    }
    
    # Process each JSON file
    for json_file in json_files:
        collection_name = json_file.stem  # filename without extension
        
        print(f"\n{'=' * 60}")
        print(f"📋 Processing collection: {collection_name}")
        print(f"{'=' * 60}")
        
        stats["total_collections"] += 1
        
        # Clear the collection
        clear_result = clear_collection(mongo_client, db_name, collection_name)
        
        if not clear_result.get("success", False):
            print(f"⚠️ Failed to clear collection '{collection_name}'")
            stats["failed_collections"].append(collection_name)
            continue
        
        stats["total_documents_cleared"] += clear_result.get("deleted_count", 0)
        
        # Load JSON data
        try:
            with open(json_file, 'r') as f:
                documents = json.load(f)
            
            if not isinstance(documents, list):
                print(f"⚠️ JSON file '{json_file.name}' should contain an array of documents")
                stats["failed_collections"].append(collection_name)
                continue
            
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON file '{json_file.name}': {e}")
            stats["failed_collections"].append(collection_name)
            continue
        except Exception as e:
            print(f"❌ Error reading file '{json_file.name}': {e}")
            stats["failed_collections"].append(collection_name)
            continue
        
        # Load data into collection
        load_result = load_collection_data(mongo_client, db_name, collection_name, documents)
        
        if not load_result.get("success", False):
            stats["failed_collections"].append(collection_name)
        else:
            stats["total_documents_inserted"] += load_result.get("inserted_count", 0)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📈 SUMMARY")
    print("=" * 60)
    print(f"✅ Collections processed: {stats['total_collections']}")
    print(f"🗑️ Total documents cleared: {stats['total_documents_cleared']}")
    print(f"📥 Total documents inserted: {stats['total_documents_inserted']}")
    
    if stats["failed_collections"]:
        print(f"❌ Failed collections ({len(stats['failed_collections'])}): {', '.join(stats['failed_collections'])}")
    else:
        print("✨ All collections loaded successfully!")
    
    print("=" * 60)
    print("🎉 Test data load complete")
    print("=" * 60)


if __name__ == "__main__":
    try:
        load_all_test_data()
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

