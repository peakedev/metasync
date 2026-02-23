"""
Stream API router
Provides streaming LLM responses with client authentication
"""
import time
import asyncio
import threading
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from typing import Annotated, Optional, List

from api.middleware.client_auth import verify_client_auth
from api.models.stream_models import (
    StreamCreateRequest,
    StreamResponse,
    StreamSummaryResponse,
    StreamStatus
)
from api.services.stream_service import get_stream_service
from api.core.logging import get_logger
from config import config
from llm_sdks.registry import SDKRegistry

logger = get_logger("api.routers.stream")

router = APIRouter()

# Sentinel for signaling end-of-stream from a sync generator
_STREAM_END = object()


def _next_chunk(gen):
    """Advance a sync generator by one step.

    Returns the yielded chunk on success, or a
    (_STREAM_END, return_value) tuple when the generator
    is exhausted.  This wrapper exists because
    StopIteration cannot propagate through
    ``asyncio.to_thread`` into an async generator
    (PEP 479 converts it to RuntimeError).
    """
    try:
        return next(gen)
    except StopIteration as e:
        return (_STREAM_END, e.value)


@router.get("", response_model=List[StreamResponse])
async def list_streams(
    client_id: str = Depends(verify_client_auth),
    model: Optional[str] = Query(None, description="Filter by model"),
    status: Optional[str] = Query(None, description="Filter by status (streaming, completed, error)"),
    limit: Optional[int] = Query(
        None, description="Limit the number of results returned", ge=1
    )
):
    """
    List streams with optional filters.

    - Requires client authentication (client_id and client_api_key headers)
    - Returns only streams belonging to the authenticated client
    - Supports filtering by model and status via query parameters
    - Supports limiting results with the limit parameter (e.g., limit=10 returns only 10 items)
    """
    try:
        service = get_stream_service()

        streams = service.list_streams(
            client_id=client_id,
            model=model,
            status=status,
            limit=limit
        )

        return [StreamResponse(
            streamId=stream["streamId"],
            clientId=stream["clientId"],
            model=stream["model"],
            temperature=stream["temperature"],
            status=stream["status"],
            processingMetrics=stream.get("processingMetrics"),
            _metadata=stream["_metadata"]
        ) for stream in streams]
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error listing streams", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error listing streams", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list streams"
        )


@router.get("/summary", response_model=StreamSummaryResponse)
async def get_streams_summary(
    client_id: str = Depends(verify_client_auth),
    model: Optional[str] = Query(None, description="Filter by model"),
    status: Optional[str] = Query(None, description="Filter by status (streaming, completed, error)")
):
    """
    Get summary of streams with counts by status.

    - Requires client authentication (client_id and client_api_key headers)
    - Returns counts for each status (streaming, completed, error)
    - Supports filtering by model and status
    - Clients can only see their own streams
    """
    try:
        service = get_stream_service()

        summary = service.get_streams_summary(
            client_id=client_id,
            model=model,
            status=status
        )

        return StreamSummaryResponse(**summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting stream summary", error=str(e), client_id=client_id
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get stream summary"
        )


@router.get("/{stream_id}", response_model=StreamResponse)
async def get_stream(
    stream_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Get a stream by ID.

    - Requires client authentication (client_id and client_api_key headers)
    - Clients can only access their own streams
    """
    service = get_stream_service()

    try:
        stream = service.get_stream_by_id(stream_id, client_id)

        return StreamResponse(
            streamId=str(stream["_id"]),
            clientId=stream["clientId"],
            model=stream["model"],
            temperature=stream["temperature"],
            status=stream["status"],
            processingMetrics=stream.get("processingMetrics"),
            _metadata=stream["_metadata"]
        )
    except ValueError as e:
        logger.warning("Error getting stream", error=str(e), stream_id=stream_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting stream", error=str(e), stream_id=stream_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get stream"
        )


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
    request_received_time = time.time()
    service = get_stream_service()

    try:
        # Validate model exists and get its configuration
        model_config = service.validate_model(request.model)
        model_name = model_config.get("name")
        sdk_name = model_config.get("sdk")
        max_temperature = model_config.get("maxTemperature", 1)
        min_temperature = model_config.get("minTemperature", 0)

        # Clamp temperature to model's limits
        temperature = max(
            min(request.temperature, max_temperature),
            min_temperature
        )

        # Validate and fetch prompt contents in a single DB
        # pass (replaces the old validate-then-fetch pattern
        # that issued 2N queries instead of N).
        system_prompt = ""
        if request.additionalPrompts:
            system_prompt = service.validate_and_fetch_prompts(
                request.additionalPrompts
            )

        # Get API key for the model
        if sdk_name != "test":
            api_key = config.get_model_key(model_name)
            if not api_key:
                raise ValueError(
                    f"API key not found for model '{model_name}'"
                )
        else:
            api_key = None

        # Get SDK implementation
        sdk_impl = SDKRegistry.get_sdk(sdk_name)
        if sdk_impl is None:
            raise ValueError(f"Unsupported SDK type: {sdk_name}")

    except ValueError as e:
        logger.warning(
            "Validation error in stream request", error=str(e)
        )
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

    # Pre-generate stream ID so the response header is
    # available immediately and the DB write can run in the
    # background without blocking time-to-first-byte.
    stream_id = str(ObjectId())

    request_data = {
        "userPrompt": request.userPrompt,
        "additionalPrompts": request.additionalPrompts,
        "systemPrompt": system_prompt if system_prompt else None
    }

    # Fire DB record creation in a background thread so it
    # does not block the streaming response.
    def _create_record():
        try:
            service.create_stream_record(
                client_id=client_id,
                model=request.model,
                temperature=temperature,
                request_data=request_data,
                stream_id=stream_id
            )
        except Exception as exc:
            logger.error(
                "Failed to create stream record",
                error=str(exc), stream_id=stream_id
            )

    threading.Thread(target=_create_record, daemon=True).start()

    # Define the streaming generator
    async def generate_stream():
        """Generate streaming response chunks."""
        llm_start_time = time.time()
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
                max_tokens=(
                    model_config.get("maxCompletionToken")
                    or model_config.get("maxToken", 100000)
                ),
                api_key=api_key
            )

            # Iterate the sync generator via the thread pool
            # so the event loop is never blocked waiting for
            # the next chunk from the LLM provider.
            while True:
                result = await asyncio.to_thread(
                    _next_chunk, stream_generator
                )
                if (isinstance(result, tuple)
                        and len(result) == 2
                        and result[0] is _STREAM_END):
                    token_info = result[1]
                    if token_info and len(token_info) == 3:
                        (prompt_tokens, completion_tokens,
                         total_tokens) = token_info
                    break
                full_response.append(result)
                yield result

            llm_end_time = time.time()
            llm_duration = llm_end_time - llm_start_time

            # Build response data and processing metrics
            response_data = {
                "text": "".join(full_response)
            }

            processing_metrics = {
                "inputTokens": prompt_tokens,
                "outputTokens": completion_tokens,
                "totalTokens": total_tokens,
                "llmDuration": round(llm_duration, 2)
            }

            # Calculate cost if model has cost config
            cost_info = model_config.get("cost")
            if cost_info:
                cost_input = cost_info.get("input")
                cost_output = cost_info.get("output")
                cost_tokens = cost_info.get("tokens")
                currency = cost_info.get("currency")

                if (cost_input is not None
                        and cost_output is not None
                        and cost_tokens is not None
                        and currency):
                    in_cost = (
                        (prompt_tokens / cost_tokens) * cost_input
                    )
                    out_cost = (
                        (completion_tokens / cost_tokens)
                        * cost_output
                    )
                    processing_metrics["inputCost"] = in_cost
                    processing_metrics["outputCost"] = out_cost
                    processing_metrics["totalCost"] = (
                        in_cost + out_cost
                    )
                    processing_metrics["currency"] = currency

            request_end_time = time.time()
            total_duration = (
                request_end_time - request_received_time
            )
            overhead_duration = total_duration - llm_duration

            processing_metrics["duration"] = round(
                total_duration, 2
            )
            processing_metrics["totalDuration"] = round(
                total_duration, 2
            )
            processing_metrics["overheadDuration"] = round(
                overhead_duration, 2
            )

            # Fire DB update in background — the caller
            # already received the full streamed response so
            # there is no reason to block here.
            def _update_record():
                try:
                    service.update_stream_record(
                        stream_id=stream_id,
                        response_data=response_data,
                        processing_metrics=processing_metrics,
                        status="completed"
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to update stream record",
                        error=str(exc),
                        stream_id=stream_id
                    )

            threading.Thread(
                target=_update_record, daemon=True
            ).start()

            logger.info(
                "Stream completed",
                stream_id=stream_id,
                total=f"{total_duration:.2f}s",
                llm=f"{llm_duration:.2f}s",
                overhead=f"{overhead_duration:.2f}s"
            )

        except Exception as e:
            logger.error(
                "Error during streaming",
                error=str(e), stream_id=stream_id
            )

            request_end_time = time.time()
            llm_duration = request_end_time - llm_start_time
            total_duration = (
                request_end_time - request_received_time
            )
            overhead_duration = total_duration - llm_duration

            err_metrics = {
                "duration": round(total_duration, 2),
                "llmDuration": round(llm_duration, 2),
                "totalDuration": round(total_duration, 2),
                "overheadDuration": round(
                    overhead_duration, 2
                ),
                "error": str(e)
            }

            def _update_error():
                try:
                    service.update_stream_record(
                        stream_id=stream_id,
                        response_data={"error": str(e)},
                        processing_metrics=err_metrics,
                        status="error"
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to update error record",
                        error=str(exc),
                        stream_id=stream_id
                    )

            threading.Thread(
                target=_update_error, daemon=True
            ).start()

            # Don't raise — stream already started
            yield f"\n\n[Error: {str(e)}]"

    # Return StreamingResponse immediately
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "X-Stream-Id": stream_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
