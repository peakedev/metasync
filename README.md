# Metasync

## Description

Metasync is an async LLM-processing pipeline designed to handle high-volume prompt workloads across multiple model providers. It manages queue-based request ingestion, parallel processing, and result aggregation, while also providing an integrated metaprompting optimization pipeline that helps client optimize and evaluate prompts before they hit the underlying models. The result is a scalable, fault-tolerant engine for automated LLM orchestration, optimization, and batch processing.

## Why Metasync?

This project was built as many, because we didn't find anything that fitted exactly the needs, but we hope it can be used by other.

## Docker Hub

The Metasync Docker image is available on Docker Hub:

**https://hub.docker.com/r/peakedev/metasync**

## Future Plans

In time, we want to add a layer of abstraction to allow orchestration of many LLM tasks, automated handling of model rate limiters, built-in multi-provider failover routing, evaluation pipelines, and long-running background jobs.

# 1.0.0
- True runtime statelessness with distributed semaphore for thread management & thread at worker level
- Auto mode with (parametrised) model router as entry point (support for 'model forwarding') 
- High level worker controls (Total estimate cost; Rate limiting in Tokens per minute)
- User Interface 

## Project Structure

```
├── api/                     # FastAPI application
│   ├── core/               # Authentication and logging utilities
│   ├── middleware/         # Auth middleware for requests
│   ├── models/             # Pydantic data models
│   ├── routers/            # API endpoint routes
│   └── services/           # Business logic and data services
├── llm_optimizers/         # Run orchestration and optimization logic
├── llm_sdks/               # Pluggable LLM provider integrations
├── llm_workers/            # Background queue workers for LLM processing
├── utilities/              # Database connectors and helper functions
├── tests/                  # Bruno API tests and test data
├── config.py               # Application configuration
├── main_app.py             # Application entry point
└── requirements.txt        # Python dependencies
```

## LLM SDK Plugin Architecture

Metasync uses a modular, plugin-based architecture for LLM SDK integrations. Each SDK is implemented as a separate plugin in the `llm_sdks/` directory.

### Supported SDKs

- **ChatCompletionsClient** - Azure AI Inference SDK
- **AzureOpenAI** - Azure OpenAI via official OpenAI SDK
- **Anthropic** - Anthropic Claude with streaming support
- **test** - Mock SDK for testing (no API calls)

### Key Features

- **Auto-Discovery** - New SDKs are automatically discovered by scanning `llm_sdks/`
- **Zero Configuration** - No need to modify core code when adding SDKs
- **SDK-Specific Validation** - Each SDK validates its own configuration requirements
- **PEP8 Compliant** - All SDK code follows strict Python style guidelines
- **Modular & Testable** - Each SDK is self-contained and independently testable

### Adding a New SDK

To add support for a new LLM provider:

1. Create a new file in `llm_sdks/` named after your SDK (e.g., `MySdk.py`)
2. Inherit from `BaseLLMSDK` and implement three required methods:
   - `get_name()` - Returns the SDK identifier
   - `validate_config(config)` - Validates SDK-specific requirements
   - `complete(...)` - Executes the completion request
3. Your SDK will be automatically discovered and available

See `llm_sdks/README.md` for a comprehensive guide with examples.

### Architecture Benefits

- **Extensibility** - Add new SDKs without touching core code
- **Maintainability** - SDK-specific logic isolated in individual files
- **Backward Compatibility** - Existing SDKs and models unchanged
- **Type Safety** - Abstract base class ensures consistent interface

## Environment Variables

### Required Environment Variables

- **DB_CONNECTION_STRING** — MongoDB/CosmosDB connection string (required; raises error if missing)
- **DOCS_SECRET** — Password for protected documentation endpoints (required; raises error if missing)
- **API_KEY_PEPPER** — Secret used for API key hashing/validation (required via keyring)
- **ADMIN_API_KEY** — Admin API key for privileged operations (required via keyring)

### Optional Environment Variables (with defaults)

- **DB_NAME** — Database name (default: `"poc-llm-processor"`)
- **DOCS_USER** — Username for documentation authentication (default: `"user"`)
- **POLL_INTERVAL** — Worker polling interval in seconds (default: `"10"`)
- **MAX_ITEMS_PER_BATCH** — Maximum items per batch processing (default: `"50"`)
- **NUM_LLM_WORKERS** — Number of LLM worker threads (default: `"10"`)

### Dynamic Model-Specific Keys

Model API keys are loaded dynamically based on models stored in the database. Each model requires an environment variable following this pattern:

**{MODEL_NAME}_KEY** — Where `MODEL_NAME` is converted to uppercase with special characters replaced (e.g., `"gpt-4"` becomes `GPT_4_KEY`)

These are referenced in `config.py` when models are loaded from the database.

**Note:** The test SDK does not require an API key and can be used for testing without credentials.

### Summary for docker-compose

From `docker-compose.yaml`, these are passed to the container:

- `DB_NAME`
- `DB_CONNECTION_STRING`
- `DOCS_USER`
- `DOCS_SECRET`
- `API_KEY_PEPPER`
- `ADMIN_API_KEY`
- `POLL_INTERVAL`
- `MAX_ITEMS_PER_BATCH`
- `NUM_LLM_WORKERS`

**Note:** The application uses a keyring fallback for secrets (macOS Keychain), but in containerized environments, you should provide all required secrets as environment variables.

