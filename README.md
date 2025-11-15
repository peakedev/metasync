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

## 1.0.0 To Dos

- Describe usage better
- Describe how to extend
- Properly modularise LLM client config to let users add LLM clients easily
- Add a sync API for testing and quick access to models
- Self-contained testing with Mongo Container and DB Seed (/test/mongo)
- Remove tests/shell
- Add auto bruno regression when building
- Full stable API with more edge-case before graduating to 1.0
- Address statelessness & challenge with multithreaded workers defined within the replicas
- Ensure the llm-optimiser functionalities are fully API enabled and working in the framework
- Chain or Embed the evaluation step (optionally) separately from the llm-optimizer but still compatible with the optimization routines

## Project Structure

```
├── api/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── docs_auth.py
│   │   └── logging.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── client_auth.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── client_models.py
│   │   ├── job_models.py
│   │   ├── model_models.py
│   │   ├── prompt_flow_models.py
│   │   ├── prompt_models.py
│   │   └── worker_models.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── clients.py
│   │   ├── health.py
│   │   ├── jobs.py
│   │   ├── models.py
│   │   ├── prompt_flows.py
│   │   ├── prompts.py
│   │   └── workers.py
│   └── services/
│       ├── __init__.py
│       ├── client_service.py
│       ├── job_service.py
│       ├── model_service.py
│       ├── prompt_flow_service.py
│       ├── prompt_service.py
│       ├── worker_manager.py
│       └── worker_service.py
├── llm-optimizer/
│   ├── opti_inqueue_handler.py
│   ├── opti_outqueue_handler.py
│   ├── opti_prompt_handler.py
│   ├── optimisation_services/
│   │   ├── __init__.py
│   │   ├── core.py
│   │   ├── evaluation.py
│   │   └── meta_prompter.py
│   ├── optimizer_orchestrator.py
│   └── workflows/
│       ├── __init__.py
│       ├── combi_runner.py
│       ├── init_runner.py
│       ├── iteration_runner_workers.py
│       └── operations_handler.py
├── llm-workers/
│   └── llm_queue_worker.py
├── utilities/
│   ├── cosmos_connector.py
│   ├── json_repair.py
│   ├── keyring_handler.py
│   └── llm_connector.py
├── tests/
│   ├── bruno/
│   └── shell/
├── config.py
├── docker-compose.yaml
├── Dockerfile
├── env.json
├── main_app.py
└── requirements.txt
```

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

