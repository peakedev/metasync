# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**Metasync** is an async LLM-processing pipeline designed to handle high-volume prompt workloads across multiple model providers. It manages queue-based request ingestion, parallel processing, and result aggregation, while providing an integrated metaprompting optimization pipeline.

## Technology Stack

- **Framework**: FastAPI (Python 3.x)
- **Database**: MongoDB/CosmosDB
- **Authentication**: API key-based (client + admin)
- **Logging**: structlog
- **LLM Providers**: Azure OpenAI, Azure AI Inference, Anthropic Claude, Google Gemini

## Project Structure

```
├── api/                     # FastAPI application
│   ├── core/               # Auth utilities, logging
│   ├── middleware/         # Auth middleware (admin, client)
│   ├── models/             # Pydantic data models
│   ├── routers/            # API endpoint routes
│   └── services/           # Business logic layer
├── llm_optimizers/         # Run orchestration and optimization
├── llm_sdks/               # Pluggable LLM provider integrations
├── llm_workers/            # Background queue workers
├── utilities/              # Database connectors, helpers
├── tests/                  # Bruno API tests
├── config.py               # Singleton configuration factory
└── main_app.py             # Application entry point
```

## Architecture Patterns

### 1. Layered Architecture
- **Routers** (`api/routers/`): Handle HTTP requests, validation, response formatting
- **Services** (`api/services/`): Business logic, access control, database operations
- **Models** (`api/models/`): Pydantic schemas for request/response validation

### 2. Singleton Pattern
Used throughout for global state management:
- `ConfigFactory` in `config.py`
- Service instances via `get_*_service()` factory functions
- `ClientManager` for MongoDB connection pooling

### 3. Plugin Architecture (LLM SDKs)
All LLM providers implement `BaseLLMSDK` from `llm_sdks/base_sdk.py`:
```python
class BaseLLMSDK(ABC):
    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> None: ...

    @abstractmethod
    def complete(self, config, system_prompt, user_content,
                 temperature, max_tokens, api_key) -> Tuple[str, int, int, int]: ...

    @abstractmethod
    def stream(self, config, system_prompt, user_content,
               temperature, max_tokens, api_key) -> Generator[str, None, Tuple[int, int, int]]: ...
```

### 4. Authentication Pattern
Two auth types handled via FastAPI dependencies:
- **Admin auth**: `verify_admin_api_key()` - constant-time comparison
- **Client auth**: `verify_client_auth()` - validates client_id + client_api_key
- **Optional auth**: `optional_client_auth()`, `optional_admin_auth()` - returns None if invalid

## Coding Conventions

### Python Style
- **PEP8 compliant** with 79-character line limit
- Use **type hints** for all function parameters and return values
- Use **docstrings** for all public functions with Args/Returns/Raises sections
- Imports ordered: stdlib, third-party, local (alphabetically within groups)

### Naming Conventions
- **Files**: snake_case (e.g., `job_service.py`, `job_models.py`)
- **Classes**: PascalCase (e.g., `JobService`, `JobCreateRequest`)
- **Functions/methods**: snake_case (e.g., `get_job_by_id`)
- **Constants**: UPPER_SNAKE_CASE
- **API fields**: camelCase in JSON (Pydantic handles conversion)

### Pydantic Models
```python
class ExampleRequest(BaseModel):
    """Request model with validation"""
    field_name: str = Field(..., description="Field description", min_length=1)
    optional_field: Optional[str] = Field(None, description="Optional field")

    @field_validator('field_name')
    @classmethod
    def validate_field(cls, v):
        # Custom validation logic
        return v
```

### Router Pattern
```python
@router.post("", response_model=ResponseModel, status_code=http_status.HTTP_201_CREATED)
async def create_resource(
    request: CreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Endpoint docstring with description.

    - Bullet points for behavior
    - Returns description
    """
    try:
        service = get_service()
        result = service.create(...)
        return ResponseModel(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error message", error=str(e))
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Generic error")
```

### Service Pattern
```python
class ExampleService:
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "collection"
        self._cached_client = None

    @property
    def mongo_client(self):
        """Get a valid MongoDB client with connection pooling."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(
            self._connection_string, self._cached_client
        )
        return self._cached_client
```

### Error Handling
- Use `ValueError` for validation/business logic errors
- Use `RuntimeError` for database/system failures
- Log errors with context: `logger.error("Message", error=str(e), context=value)`
- Return appropriate HTTP status codes (400 for validation, 404 for not found, 500 for system)

### Logging
```python
from api.core.logging import get_logger, BusinessLogger

logger = get_logger("api.module.name")
business_logger = BusinessLogger()

# Standard logging
logger.info("Operation completed", field=value, another_field=value)
logger.warning("Warning message", error=str(e))
logger.error("Error occurred", error=str(e), context=context)

# Business operation logging
business_logger.log_operation("service", "operation", client_id=client_id)
business_logger.log_error("service", "operation", "Error description")
```

## Database Conventions

### Document Structure
All documents include metadata:
```python
{
    "_id": ObjectId,
    "field": "value",
    "_metadata": {
        "isDeleted": False,
        "createdAt": datetime,
        "updatedAt": datetime,
        "deletedAt": None,
        "createdBy": None,
        "updatedBy": None,
        "deletedBy": None
    }
}
```

### Soft Delete
All deletes are soft deletes - set `_metadata.isDeleted = True` and `_metadata.deletedAt`.
Always filter by `_metadata.isDeleted != True` when reading.

### Database Operations
Use utilities from `cosmos_connector.py`:
- `db_create()` - Insert document
- `db_read()` - Query documents
- `db_find_one()` - Find single document
- `db_update()` - Update document
- `db_delete()` - Soft delete document
- `get_document_by_id()` - Get by ObjectId
- `safe_operation()` - Retry wrapper for operations

## Security Guidelines

### Authentication
- Always use constant-time comparison for API keys (`secrets.compare_digest`)
- Never log API keys or secrets
- Validate client ownership before any operation

### Access Control
```python
def _check_job_access(self, job, client_id, is_admin=False) -> bool:
    if is_admin:
        return True
    if not client_id:
        return False
    return job.get("clientId") == client_id
```

### Input Validation
- Validate all prompt IDs exist before creating jobs
- Validate all model names exist before processing
- Validate state transitions are allowed

## Adding New Features

### Adding a New LLM SDK
1. Create file in `llm_sdks/` (e.g., `NewProvider.py`)
2. Inherit from `BaseLLMSDK`
3. Implement `get_name()`, `validate_config()`, `complete()`, `stream()`
4. SDK auto-discovered via registry

### Adding a New API Endpoint
1. Create/update model in `api/models/`
2. Create/update service in `api/services/`
3. Create/update router in `api/routers/`
4. Include router in `main_app.py` if new file

### Adding a New Collection
1. Add collection name constant to relevant service
2. Create Pydantic models for the collection
3. Create service class with CRUD operations
4. Create router with endpoints
5. Update `README.md` if user-facing

## Testing

### Bruno API Tests
Tests are in `tests/bruno/` directory using Bruno HTTP client format.
- Environment files in `tests/bruno/environments/`
- Use `sample.bru` files as templates

### Running Tests
```bash
# Run API tests with Bruno CLI
bru run tests/bruno --env dev
```

## Environment Variables

### Required
- `DB_CONNECTION_STRING` - MongoDB/CosmosDB connection
- `DOCS_SECRET` - Documentation endpoint password
- `API_KEY_PEPPER` - Client API key hashing secret
- `ADMIN_API_KEY` - Admin authentication key

### Optional (with defaults)
- `DB_NAME` - Database name (default: "metasync-dev")
- `DOCS_USER` - Docs username (default: "user")
- `POLL_INTERVAL` - Worker poll interval seconds (default: "10")
- `MAX_ITEMS_PER_BATCH` - Batch size (default: "50")
- `NUM_LLM_WORKERS` - Worker thread count (default: "10")

### Model Keys
Dynamic: `{MODEL_NAME}_KEY` where MODEL_NAME is uppercase with special chars replaced.
Example: `gpt-4` becomes `GPT_4_KEY`

## Common Patterns to Follow

### Backward Compatibility
When deprecating fields, support both old and new:
```python
# Support both 'prompts' (deprecated) and 'workingPrompts' (new)
final_prompts = working_prompts if working_prompts else prompts
```

### State Machine Transitions
Define allowed transitions explicitly:
```python
client_transitions = {
    JobStatus.PENDING: [JobStatus.CANCELED],
    JobStatus.PROCESSED: [JobStatus.CONSUMED, JobStatus.ERROR_CONSUMING],
}
```

### Batch Operations
Always validate entire batch before processing (all-or-nothing):
```python
# First pass: validate all
for item in items:
    validate(item)

# Second pass: process all
for item in items:
    process(item)
```

## Quick Reference

### Start the Application
```bash
python main_app.py
# or
uvicorn main_app:app --host 0.0.0.0 --port 8001
```

### Docker
```bash
docker-compose up
```

### API Documentation
Protected endpoints at `/docs` and `/redoc` (require DOCS_USER/DOCS_SECRET).
