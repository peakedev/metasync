#!/usr/bin/env python3
"""
Queue Worker - Processes items from the jobs collection
"""
import os
import sys
import time
import json
import re
import argparse
import threading
import traceback
from pathlib import Path
from typing import Dict, Any, Optional


# Add utilities to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "utilities"))
sys.path.insert(0, str(project_root))
from utilities.cosmos_connector import (
    get_mongo_client,
    db_read,
    db_update,
    db_create,
    get_document_by_id
)
from utilities.llm_connector import complete_with_model
from utilities.json_repair import (
    repair_json_comprehensive,
    validate_json
)

# Import centralized configuration
from config import config

# Use centralized configuration
queue_db_name = config.db_name  # Use db_name from config
poll_interval = config.poll_interval
max_items_per_batch = config.max_items_per_batch


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model_config: Dict[str, Any],
    log_level: str = "INFO"
) -> Optional[Dict[str, Any]]:
    """
    Estimate the cost of LLM processing.
    
    Based on token usage and model pricing.
    
    Args:
        input_tokens: Number of input/prompt tokens used
        output_tokens: Number of output/completion tokens used
        model_config: Model configuration dictionary containing cost
            information
        log_level: Logging level to control debug output
        
    Returns:
        Dictionary with 'input_cost', 'output_cost', and 'currency' keys,
        or None if cost info is missing
    """
    model_name = model_config.get("name", "unknown")
    
    # Extract cost information from model_config
    cost_info = model_config.get("cost")
    if not cost_info:
        if log_level == "DEBUG":
            print(f"  ⚠️ No 'cost' field found in model config for '{model_name}'")
        return None
    
    cost_input = cost_info.get("input")
    cost_output = cost_info.get("output")
    cost_tokens = cost_info.get("tokens")
    currency = cost_info.get("currency")
    
    # If any required cost field is missing, return None
    if cost_input is None or cost_output is None or cost_tokens is None or not currency:
        missing_fields = []
        if cost_input is None:
            missing_fields.append("input")
        if cost_output is None:
            missing_fields.append("output")
        if cost_tokens is None:
            missing_fields.append("tokens")
        if not currency:
            missing_fields.append("currency")
        
        if log_level == "DEBUG":
            print(
                f"  ⚠️ Missing cost fields in model config for "
                f"'{model_name}': {', '.join(missing_fields)}"
            )
            print(f"  📋 Cost info structure: {cost_info}")
        return None
    
    # Calculate costs: (tokens / cost.tokens) * cost.price
    input_cost = (input_tokens / cost_tokens) * cost_input
    output_cost = (output_tokens / cost_tokens) * cost_output
    
    if log_level == "DEBUG":
        print(
            f"  💰 Cost calculated for '{model_name}': "
            f"input=${input_cost:.6f}, output=${output_cost:.6f} {currency}"
        )
    
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "currency": currency
    }


class QueueWorker:
    """Worker class for processing jobs from the queue."""
    
    def __init__(
        self,
        worker_id: str,
        client_id: str,
        connection_string: str = None,
        db_name: str = None,
        poll_interval: int = None,
        max_items_per_batch: int = None,
        exit_when_empty: bool = False,
        log_level: str = "INFO",
        model_filter: Optional[str] = None,
        operation_filter: Optional[str] = None,
        client_reference_filters: Optional[Dict[str, str]] = None,
        stop_event: Optional[threading.Event] = None
    ):
        """
        Initialize the queue worker with database connection.
        
        Args:
            worker_id: Unique identifier for this worker
            client_id: Client ID that owns this worker (required for
                filtering)
            connection_string: MongoDB connection string (uses config if
                not provided)
            db_name: Database name (uses config if not provided)
            poll_interval: Polling interval in seconds (uses config if
                not provided)
            max_items_per_batch: Maximum items to process per batch (uses
                config if not provided)
            exit_when_empty: Exit when no pending items found (for script
                mode)
            log_level: Logging level (INFO or DEBUG)
            model_filter: Optional filter for model name
            operation_filter: Optional filter for operation type
            client_reference_filters: Optional dict of clientReference
                field filters (exact match)
            stop_event: Optional threading.Event to signal worker to stop
        """
        self.worker_id = worker_id
        self.client_id = client_id
        self.exit_when_empty = exit_when_empty
        self.log_level = log_level.upper()
        self.model_filter = model_filter
        self.operation_filter = operation_filter
        self.client_reference_filters = client_reference_filters or {}
        self.stop_event = stop_event or threading.Event()
        
        # Use provided values or fall back to config
        self.connection_string = connection_string
        self.db_name = db_name or queue_db_name
        self.poll_interval = poll_interval or config.poll_interval
        self.max_items_per_batch = (
            max_items_per_batch or config.max_items_per_batch
        )
        
        try:
            # Get connection string if not provided
            if not self.connection_string:
                self.connection_string = config.db_connection_string
            
            self.mongo_client = get_mongo_client(self.connection_string)
            self.db = self.mongo_client[self.db_name]
            if self.log_level == "DEBUG":
                print(f"✅ Connected to database: {self.db_name}")
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            raise

    def fetch_pending_items(self, limit: int = 10) -> list:
        """
        Fetch pending items from the jobs collection.
        
        Ordered by priority (lower first). Applies client-specific and
        optional filters.

        Args:
            limit (int): Maximum number of items to fetch

        Returns:
            list: List of pending items ordered by priority
        """
        try:
            # Base query: status must be PENDING and must belong to this client
            query = {
                "status": "PENDING",
                "clientId": self.client_id
            }

            # Add model filter if specified
            if self.model_filter:
                query["model"] = self.model_filter

            # Add operation filter if specified
            if self.operation_filter:
                query["operation"] = self.operation_filter

            # Add clientReference filters if specified (exact match for
            # nested fields)
            if self.client_reference_filters:
                for key, value in self.client_reference_filters.items():
                    query[f"clientReference.{key}"] = value

            # Fetch items with sorting by priority (ascending - lower
            # numbers first)
            # NOTE: Requires a composite index on (status, clientId,
            # priority) in Cosmos DB for this query to work efficiently.
            # Without the index, Cosmos DB will return an error: "The index
            # path corresponding to the specified order-by item is
            # excluded."
            db = self.mongo_client[self.db_name]
            collection = db["jobs"]

            # Apply query and sort by priority (1 = ascending)
            cursor = collection.find(query).sort("priority", 1).limit(limit)
            items = list(cursor)

            return items
        except Exception as e:
            print(f"❌ Error fetching pending items: {e}")
            return []

    def fetch_prompt(self, prompt_id: str) -> Optional[str]:
        """
        Fetch prompt content by prompt ID.
        
        Args:
            prompt_id: The MongoDB _id of the prompt document
            
        Returns:
            The prompt text content, or None if not found
        """
        try:
            prompt_doc = get_document_by_id(
                self.mongo_client, self.db_name, "prompts", prompt_id
            )
            
            if prompt_doc:
                return prompt_doc.get("prompt", "")
            else:
                print(f"⚠️ Prompt not found: {prompt_id}")
                return None
        except Exception as e:
            print(f"❌ Error fetching prompt {prompt_id}: {e}")
            return None

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get model configuration from database."""
        try:
            # Fetch model configuration
            query = {"name": model_name}
            model_configs = db_read(
                self.mongo_client,
                self.db_name,
                "models",
                query=query,
                limit=1
            )

            if not model_configs:
                print(f"⚠️ Model not found: {model_name}")
                return None

            model_conf = model_configs[0]
            return model_conf
        except Exception as e:
            print(f"❌ Error getting model config for {model_name}: {e}")
            return None

    def atomic_status_update(
        self,
        item_id: str,
        from_status: str,
        to_status: str,
        additional_updates: dict = None
    ) -> bool:
        """
        Atomically update item status from one status to another.
        
        This prevents race conditions when multiple workers try to pick up
        the same item.

        Args:
            item_id (str): The _id of the item to update
            from_status (str): Current status that must match for update
                to succeed
            to_status (str): New status to set
            additional_updates (dict): Additional fields to update

        Returns:
            bool: True if update was successful, False if another worker
                got there first
        """
        try:
            from bson import ObjectId
            from datetime import datetime

            db = self.mongo_client[self.db_name]
            collection = db["jobs"]

            # Prepare the update document
            update_doc = {"$set": {"status": to_status}}
            if additional_updates:
                for key, value in additional_updates.items():
                    update_doc["$set"][key] = value

            # Add metadata
            update_doc["$set"]["_metadata.updatedAt"] = (
                datetime.now().isoformat()
            )

            # Use findOneAndUpdate with atomic condition
            result = collection.find_one_and_update(
                {"_id": ObjectId(item_id), "status": from_status},
                update_doc,
                return_document=False  # Return the document before update
            )

            # If result is None, it means the status wasn't "from_status"
            # (another worker got it)
            return result is not None

        except Exception as e:
            print(f"❌ Error in atomic status update: {e}")
            return False

    def process_item(self, item: Dict[str, Any]) -> bool:
        """Process a single item from the queue."""
        item_id = str(item.get("_id"))
        friendly_name = str(item.get("id"))
        display_name = (
            f"{friendly_name} ({item_id})"
            if friendly_name != item_id else item_id
        )
        print(f"\n{'='*60}")
        print(f"🔄 Worker {self.worker_id}: Processing item {display_name}")
        print(f"{'='*60}")

        # First, mark item as processing to prevent other workers from
        # picking it up
        if self.log_level == "DEBUG":
            print(f"  🔄 Marking item as processing...")
        processing_updates = {}

        # Use atomic update to only change status if it's currently
        # "PENDING"
        processing_success = self.atomic_status_update(
            item_id, "PENDING", "PROCESSING", processing_updates
        )
        if not processing_success:
            if self.log_level == "DEBUG":
                print(
                    f"  ❌ Failed to mark item as processing - another "
                    f"worker may have picked it up"
                )
            return False

        if self.log_level == "DEBUG":
            print(
                f"  ✅ Item marked as processing - proceeding with LLM "
                f"processing"
            )

        try:
            # Extract item data (support both old "data" and new
            # "requestData" field names)
            data = item.get("requestData", item.get("data", {}))
            prompts = item.get("prompts", [])
            model_name = item.get("model")
            temperature = item.get("temperature")
            client_id = item.get("clientId")
            priority = item.get("priority")
            job_id = item.get("id")  # The friendly job ID
            operation = item.get("operation")

            # Validate required fields
            if not data:
                raise ValueError(
                    "No data found in item - item may have empty "
                    "base_language content"
                )

            if not prompts:
                raise ValueError("No prompts found in item")

            if not model_name:
                raise ValueError("No model specified in item")

            # Check if data is empty or None
            if data is None or (isinstance(data, str) and not data.strip()):
                raise ValueError(
                    "Item data is empty or None - base_language content "
                    "may be missing"
                )

            # Process all prompts in order without categorization
            all_prompts = []
            prompt_ids = []

            for prompt_ref in prompts:
                # Handle both string IDs and dict format (for backward
                # compatibility)
                prompt_id = None
                if isinstance(prompt_ref, dict):
                    # Legacy format: extract ID if present, otherwise skip
                    prompt_id = (
                        prompt_ref.get("promptId") or prompt_ref.get("_id")
                    )
                    if not prompt_id:
                        print(
                            f"  ⚠️ Skipping invalid prompt reference (dict "
                            f"without ID): {prompt_ref}"
                        )
                        continue
                else:
                    # New format: prompt_ref is already a string ID
                    prompt_id = prompt_ref
                
                # Ensure prompt_id is a string
                prompt_id = str(prompt_id)
                
                if self.log_level == "DEBUG":
                    print(f"  📝 Fetching prompt by ID: {prompt_id}")

                # Fetch prompt content by ID
                prompt_content = self.fetch_prompt(prompt_id)
                if not prompt_content:
                    raise ValueError(f"Could not fetch prompt: {prompt_id}")

                # Append prompt content directly without categorization
                all_prompts.append(prompt_content)
                prompt_ids.append(prompt_id)

            # Get model configuration
            model_config = self.get_model_config(model_name)
            if not model_config:
                raise ValueError(
                    f"Could not get model configuration: {model_name}"
                )

            # Combine all prompts in order
            combined_prompt = "\n\n".join(all_prompts)
            if self.log_level == "DEBUG":
                print(f"  📝 Combined {len(all_prompts)} prompts in order")

            # Prepare data for LLM (convert to string if it's a dict)
            if isinstance(data, dict):
                user_content = json.dumps(data, ensure_ascii=False, indent=2)
            else:
                user_content = str(data)

            # Check if we should stop before starting expensive LLM
            # operation
            if self.stop_event.is_set():
                if self.log_level == "DEBUG":
                    print(
                        f"  🛑 Stop signal received, aborting processing "
                        f"of item {display_name}"
                    )
                # Mark item back to PENDING so another worker can pick it
                # up
                self.atomic_status_update(item_id, "PROCESSING", "PENDING", {})
                return False

            if self.log_level == "DEBUG":
                print(f"  🤖 Running LLM with model: {model_name}")

            # Track processing time
            start_time = time.time()

            # Run through LLM connector with combined prompts
            (
                response_text,
                prompt_tokens,
                completion_tokens,
                total_tokens
            ) = complete_with_model(
                mdl=model_config,
                system_prompt=combined_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=model_config["maxToken"],
                show_timer=(self.log_level == "DEBUG")
            )

            # Calculate processing time
            processing_time = time.time() - start_time

            # Store result
            result = {
                "prompts_used": prompt_ids,  # Store list of prompt IDs
                "response": response_text,
                "tokens": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": total_tokens
                },
                "model": model_name,
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.log_level == "DEBUG":
                print(f"  ✅ LLM processing completed successfully")

            # Parse the LLM response as JSON (with repair attempts)
            try:
                parsed_response = json.loads(response_text)
            except json.JSONDecodeError as e:
                # Try to repair the JSON before giving up
                if self.log_level == "DEBUG":
                    print(f"  🔧 JSON parsing failed, attempting repair: {e}")

                try:
                    # Apply comprehensive JSON repair
                    repaired_json = repair_json_comprehensive(response_text)

                    # Validate the repaired JSON before parsing
                    is_valid, validation_error = validate_json(repaired_json)
                    if not is_valid:
                        raise json.JSONDecodeError(
                            f"Repaired JSON validation failed: "
                            f"{validation_error}",
                            repaired_json,
                            0
                        )

                    # Try parsing the repaired JSON
                    parsed_response = json.loads(repaired_json)
                    if self.log_level == "DEBUG":
                        print(f"  ✅ JSON repair and validation successful!")

                except json.JSONDecodeError as repair_error:
                    # Repair failed, proceed with original error handling
                    if self.log_level == "DEBUG":
                        print(f"  ❌ JSON repair also failed: {repair_error}")
                        print(f"  📝 Raw response: {response_text[:200]}...")

                    # Categorize the JSON error for better debugging
                    error_category = "unknown"
                    error_details = str(e)

                    if "Expecting ',' delimiter" in error_details:
                        error_category = "missing_comma"
                    elif "Expecting ':' delimiter" in error_details:
                        error_category = "missing_colon"
                    elif "Expecting property name" in error_details:
                        error_category = "invalid_property"
                    elif "Unterminated string" in error_details:
                        error_category = "unterminated_string"
                    elif "Expecting value" in error_details:
                        error_category = "missing_value"
                    elif "Extra data" in error_details:
                        error_category = "extra_data"

                    # Build comprehensive error data for debugging and manual recovery
                    error_data = {
                        "errorType": "JSON_PARSING_ERROR",
                        "errorMessage": f"Failed to parse JSON response: {error_details}",
                        "exceptionType": type(e).__name__,
                        "exceptionDetails": {
                            "original": str(e),
                            "repair_attempt": str(repair_error),
                            "category": error_category,
                            "position": getattr(e, 'pos', None),
                            "line_number": getattr(e, 'lineno', None),
                            "column": getattr(e, 'colno', None)
                        },
                        "jsonParsingIssue": {
                            "category": error_category,
                            "originalError": error_details,
                            "repairAttempted": True,
                            "repairError": str(repair_error)
                        },
                        "failedResponseData": response_text,  # Full LLM response for manual recovery
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                    # Mark item as error since JSON parsing failed
                    # (atomically from PROCESSING to ERROR_PROCESSING)
                    error_updates = {
                        "errorData": error_data
                    }
                    self.atomic_status_update(
                        item_id, "PROCESSING", "ERROR_PROCESSING",
                        error_updates
                    )
                    print(
                        f"  ⚠️ Item {display_name} marked as error due to "
                        f"invalid JSON ({error_category})"
                    )
                    return True  # Continue processing other items

            # Estimate cost based on token usage
            cost_info = estimate_cost(
                prompt_tokens, completion_tokens, model_config, self.log_level
            )
            
            # Create processing metrics
            processing_metrics = {
                "inputTokens": prompt_tokens,
                "outputTokens": completion_tokens,
                "totalTokens": total_tokens,
                "duration": round(processing_time, 2)
            }
            
            # Add cost information if available
            if cost_info:
                processing_metrics["inputCost"] = cost_info["input_cost"]
                processing_metrics["outputCost"] = cost_info["output_cost"]
                processing_metrics["totalCost"] = (
                    cost_info["input_cost"] + cost_info["output_cost"]
                )
                processing_metrics["currency"] = cost_info["currency"]
            else:
                if self.log_level == "DEBUG":
                    print(
                        f"  ⚠️ Cost estimation failed - cost info will not "
                        f"be included in processing metrics"
                    )

            # Update the same job document with responseData and
            # processingMetrics
            # Update item status to processed (atomically from PROCESSING
            # to PROCESSED)
            processed_updates = {
                "responseData": parsed_response,
                "processingMetrics": processing_metrics
            }

            success = self.atomic_status_update(
                item_id, "PROCESSING", "PROCESSED", processed_updates
            )
            if success:
                print(
                    f"✅ Worker {self.worker_id}: Item {display_name} "
                    f"processed successfully"
                )
                print(f"{'='*60}")
                return True
            else:
                if self.log_level == "DEBUG":
                    print(f"❌ Failed to update item {display_name} status")
                print(f"{'='*60}")
                return False

        except Exception as e:
            error_message = str(e)
            print(
                f"❌ Worker {self.worker_id}: Error processing item "
                f"{display_name}: {error_message}"
            )

            # Build comprehensive error data for debugging
            error_data = {
                "errorType": "PROCESSING_ERROR",
                "errorMessage": error_message,
                "exceptionType": type(e).__name__,
                "exceptionDetails": {
                    "message": str(e),
                    "traceback": traceback.format_exc()
                },
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            # If we have response_text available (LLM completed but processing failed)
            # include it for potential manual recovery
            if 'response_text' in locals():
                error_data["failedResponseData"] = response_text
                error_data["llmCompleted"] = True
            else:
                error_data["failedResponseData"] = None
                error_data["llmCompleted"] = False

            # Update item status to error (atomically from PROCESSING to
            # ERROR_PROCESSING)
            error_updates = {
                "errorData": error_data
            }

            try:
                success = self.atomic_status_update(
                    item_id, "PROCESSING", "ERROR_PROCESSING", error_updates
                )
                if success:
                    if self.log_level == "DEBUG":
                        print(f"⚠️ Item {display_name} marked as error")
                else:
                    if self.log_level == "DEBUG":
                        print(
                            f"⚠️ Failed to mark item {display_name} as error "
                            f"- status may have changed"
                        )
                print(f"{'='*60}")
            except Exception as update_error:
                if self.log_level == "DEBUG":
                    print(
                        f"❌ Failed to update error status for item "
                        f"{display_name}: {update_error}"
                    )
                print(f"{'='*60}")

            return True  # Continue processing other items

    def run_worker(self):
        """Run the worker loop. Can be stopped via stop_event."""
        # Only show detailed startup info in DEBUG mode
        if self.log_level == "DEBUG":
            print(f"🚀 Starting queue worker {self.worker_id}...")
            print(f"   Client ID: {self.client_id}")
            print(f"   Poll interval: {self.poll_interval}s")
            print(f"   Max items per batch: {self.max_items_per_batch}")
            model_filter_display = (
                self.model_filter if self.model_filter else 'All models'
            )
            print(f"   Model filter: {model_filter_display}")
            operation_filter_display = (
                self.operation_filter
                if self.operation_filter else 'All operations'
            )
            print(f"   Operation filter: {operation_filter_display}")
            cr_filters_display = (
                self.client_reference_filters
                if self.client_reference_filters else 'None'
            )
            print(f"   ClientReference filters: {cr_filters_display}")
            print(f"   Database: {self.db_name}")
            print(f"   Collection: jobs")
            print(f"   Exit when empty: {self.exit_when_empty}")

        while not self.stop_event.is_set():
            try:
                if self.log_level == "DEBUG":
                    print(f"\n🔍 Worker {self.worker_id}: Polling for pending items...")

                # Fetch pending items
                pending_items = self.fetch_pending_items(limit=self.max_items_per_batch)

                if not pending_items:
                    if self.exit_when_empty:
                        if self.log_level == "DEBUG":
                            print(
                                f"📭 Worker {self.worker_id}: No pending "
                                f"items found. Exiting as requested "
                                f"(exit_when_empty=True)"
                            )
                        break
                    else:
                        if self.log_level == "DEBUG":
                            print(
                                f"📭 Worker {self.worker_id}: No pending "
                                f"items found. Waiting {self.poll_interval}s..."
                            )
                        # Use wait with timeout to allow checking stop_event
                        if self.stop_event.wait(timeout=self.poll_interval):
                            break
                        continue

                if self.log_level == "DEBUG":
                    print(
                        f"📋 Worker {self.worker_id}: Found "
                        f"{len(pending_items)} pending items"
                    )

                # Process each item
                processed_count = 0
                error_count = 0
                skipped_count = 0  # Items skipped due to race conditions

                for item in pending_items:
                    # Check if we should stop before processing each item
                    if self.stop_event.is_set():
                        break
                    
                    try:
                        success = self.process_item(item)
                        if success:
                            processed_count += 1
                        else:
                            # process_item returns False for both race
                            # conditions and actual errors. We can't
                            # distinguish here, so we'll count them as
                            # skipped (not errors)
                            skipped_count += 1
                    except Exception as item_error:
                        print(
                            f"❌ Worker {self.worker_id}: Unexpected error "
                            f"processing item: {item_error}"
                        )
                        error_count += 1

                if self.log_level == "DEBUG":
                    print(
                        f"📊 Worker {self.worker_id}: Batch complete: "
                        f"{processed_count} processed, {error_count} errors, "
                        f"{skipped_count} skipped"
                    )

                # Brief pause before next poll (check stop_event during wait)
                if self.stop_event.wait(timeout=0.5):
                    break

            except KeyboardInterrupt:
                print(f"\n🛑 Worker {self.worker_id}: Stopped by user")
                break
            except Exception as e:
                print(f"❌ Worker {self.worker_id}: Error: {e}")
                print(f"⏳ Worker {self.worker_id}: Waiting {self.poll_interval}s before retry...")
                # Use wait with timeout to allow checking stop_event
                if self.stop_event.wait(timeout=min(1.0, self.poll_interval)):
                    break
        
        # Close MongoDB connection when stopping
        # NOTE: Do not close the client here - it's managed by
        # ClientManager and may be shared. The ClientManager will handle
        # client lifecycle
        # try:
        #     if hasattr(self, 'mongo_client') and self.mongo_client:
        #         self.mongo_client.close()
        #         if self.log_level == "DEBUG":
        #             print(
        #                 f"  🔌 MongoDB connection closed for worker "
        #                 f"{self.worker_id}"
        #             )
        # except Exception as e:
        #     if self.log_level == "DEBUG":
        #         print(f"  ⚠️ Error closing MongoDB connection: {e}")
        
        print(f"🛑 Worker {self.worker_id}: Stopped")


def main():
    """Main function to run the queue worker (script mode)."""
    parser = argparse.ArgumentParser(
        description="LLM Queue Worker - Processes items from the jobs "
                    "collection"
    )
    parser.add_argument(
        "--exit-when-empty",
        action="store_true",
        help="Exit when no pending items are found in the queue "
             "(default: False)"
    )
    parser.add_argument(
        "--log-level",
        choices=["INFO", "DEBUG"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    parser.add_argument(
        "--worker-id",
        default="unknown",
        help="Worker ID for identification in logs (default: unknown)"
    )
    parser.add_argument(
        "--client-id",
        required=True,
        help="Client ID that owns this worker (required)"
    )
    parser.add_argument(
        "--model-filter",
        default="",
        help="Filter items by model (e.g., 'gpt-4o', "
             "'claude-3.5-sonnet'). Leave empty to process all models "
             "(default: empty)"
    )
    parser.add_argument(
        "--operation-filter",
        default="",
        help="Filter items by operation type (e.g., 'process'). Leave "
             "empty to process all operations (default: empty)"
    )

    args = parser.parse_args()

    try:
        worker = QueueWorker(
            worker_id=args.worker_id,
            client_id=args.client_id,
            exit_when_empty=args.exit_when_empty,
            log_level=args.log_level,
            model_filter=(
                args.model_filter if args.model_filter else None
            ),
            operation_filter=(
                args.operation_filter if args.operation_filter else None
            )
        )
        worker.run_worker()
    except Exception as e:
        print(f"❌ Failed to start worker: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
