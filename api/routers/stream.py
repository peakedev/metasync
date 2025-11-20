"""
Stream API router
Provides streaming LLM responses with client authentication
"""
import time
from fastapi import APIRouter, HTTPException, Depends
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from typing import Annotated

from api.middleware.client_auth import verify_client_auth
from api.models.stream_models import StreamCreateRequest
from api.services.stream_service import get_stream_service
from api.core.logging import get_logger
from config import config
from llm_sdks.registry import SDKRegistry

logger = get_logger("api.routers.stream")

router = APIRouter()


@router.post("")
async def stream_completion(
    request: StreamCreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Stream LLM completion in real-time.
    
    - Requires client authentication (client_id and client_api_key headers)
    - Validates model exists and additional prompt IDs if provided
    - Streams response chunks as they arrive from the LLM
    - Saves stream record to database with request/response data
    """
    service = get_stream_service()
    
    try:
        # Validate model exists and get its configuration
        model_config = service.validate_model(request.model)
        model_name = model_config.get("name")
        sdk_name = model_config.get("sdk")
        max_temperature = model_config.get("maxTemperature", 1)
        min_temperature = model_config.get("minTemperature", 0)
        
        # Clamp temperature to model's limits
        temperature = max(min(request.temperature, max_temperature), min_temperature)
        
        # Validate additional prompts if provided
        if request.additionalPrompts:
            service.validate_additional_prompts(request.additionalPrompts)
        
        # Get API key for the model
        if sdk_name != "test":
            api_key = config.get_model_key(model_name)
            if not api_key:
                raise ValueError(f"API key not found for model '{model_name}'")
        else:
            api_key = None
        
        # Get SDK implementation
        sdk_impl = SDKRegistry.get_sdk(sdk_name)
        if sdk_impl is None:
            raise ValueError(f"Unsupported SDK type: {sdk_name}")
        
        # Build system prompt from additional prompts if provided
        system_prompt = ""
        if request.additionalPrompts:
            from utilities.cosmos_connector import get_document_by_id
            client_manager = service.mongo_client
            for prompt_id in request.additionalPrompts:
                prompt_doc = get_document_by_id(
                    client_manager,
                    service.db_name,
                    "prompts",
                    prompt_id
                )
                if prompt_doc and prompt_doc.get("content"):
                    system_prompt += prompt_doc["content"] + "\n"
        
        # Create initial stream record
        request_data = {
            "userPrompt": request.userPrompt,
            "additionalPrompts": request.additionalPrompts,
            "systemPrompt": system_prompt if system_prompt else None
        }
        
        stream_id = service.create_stream_record(
            client_id=client_id,
            model=request.model,
            temperature=temperature,
            request_data=request_data
        )
        
        logger.info(
            f"Starting stream {stream_id} for client {client_id} with model {request.model}"
        )
        
    except ValueError as e:
        logger.warning("Validation error in stream request", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error setting up stream", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to setup stream"
        )
    
    # Define the streaming generator
    async def generate_stream():
        """Generate streaming response chunks."""
        start_time = time.time()
        full_response = []
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        
        try:
            # Call SDK's stream method
            stream_generator = sdk_impl.stream(
                config=model_config,
                system_prompt=system_prompt,
                user_content=request.userPrompt,
                temperature=temperature,
                max_tokens=model_config.get("maxToken", 100000),
                api_key=api_key
            )
            
            # Manually iterate to capture the return value from StopIteration
            while True:
                try:
                    chunk = next(stream_generator)
                    full_response.append(chunk)
                    yield chunk
                except StopIteration as e:
                    # The generator's return value is in e.value
                    if e.value and len(e.value) == 3:
                        prompt_tokens, completion_tokens, total_tokens = e.value
                    break
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Update stream record with response and metrics
            response_data = {
                "text": "".join(full_response)
            }
            
            processing_metrics = {
                "promptTokens": prompt_tokens,
                "completionTokens": completion_tokens,
                "totalTokens": total_tokens,
                "durationSeconds": round(duration, 2)
            }
            
            service.update_stream_record(
                stream_id=stream_id,
                response_data=response_data,
                processing_metrics=processing_metrics,
                status="completed"
            )
            
            logger.info(
                f"Completed stream {stream_id} in {duration:.2f}s, "
                f"tokens: {total_tokens}"
            )
            
        except Exception as e:
            logger.error(f"Error during streaming for {stream_id}", error=str(e))
            
            # Update stream record with error status
            duration = time.time() - start_time
            processing_metrics = {
                "durationSeconds": round(duration, 2),
                "error": str(e)
            }
            
            service.update_stream_record(
                stream_id=stream_id,
                response_data={"error": str(e)},
                processing_metrics=processing_metrics,
                status="error"
            )
            
            # Don't raise the exception - the stream is already started
            # Just log it and end the stream
            yield f"\n\n[Error: {str(e)}]"
    
    # Return StreamingResponse
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "X-Stream-Id": stream_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable proxy buffering
        }
    )

