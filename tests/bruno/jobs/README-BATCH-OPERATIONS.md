# Jobs Batch Operations

This document describes the batch operations for jobs and their test flow.

## New Endpoints

### PATCH /jobs/batch
Updates multiple jobs at once. Works the same as the single job PATCH but allows multiple jobs to be updated in a single request.

**Features:**
- All-or-nothing validation (entire batch fails if any job fails validation)
- Clients can only update their own jobs
- Admin can update any job
- Supports all update fields: status, operation, prompts, model, temperature, priority, requestData, clientReference

**Request Body:**
```json
{
  "jobs": [
    {
      "jobId": "507f1f77bcf86cd799439011",
      "priority": 500,
      "temperature": 0.9,
      "clientReference": {
        "ref": "updated-ref"
      }
    },
    ...
  ]
}
```

**Response:** Array of updated JobResponse objects

### DELETE /jobs/batch
Deletes multiple jobs at once (soft delete).

**Features:**
- All-or-nothing validation (entire batch fails if any job fails validation)
- Clients can only delete their own jobs
- Admin can delete any job

**Request Body:**
```json
{
  "jobIds": [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012",
    ...
  ]
}
```

**Response:** 204 No Content

## Test Flow

The Bruno tests are designed to run in sequence and maintain a clean database state:

1. **17-Create-Jobs-Batch.bru** - Creates 3 test jobs and stores their IDs in variables:
   - `createdBatchJobId1`
   - `createdBatchJobId2`
   - `createdBatchJobId3`

2. **30-Update-Jobs-Batch.bru** - Updates the 3 jobs created above:
   - Changes priority, temperature, and clientReference fields
   - Verifies all jobs are updated correctly

3. **31-Delete-Jobs-Batch.bru** - Deletes the 3 jobs:
   - Cleans up the database
   - Ensures no test data remains after test run

## Error Tests

Additional test files verify error handling:

- **32-Error-Batch-Update-Job-Not-Found.bru** - Verifies 400 error when trying to update non-existent job
- **33-Error-Batch-Delete-Job-Not-Found.bru** - Verifies 400 error when trying to delete non-existent job
- **34-Error-Unauthorized-Batch-Update.bru** - Verifies 401 error for unauthorized batch updates
- **35-Error-Unauthorized-Batch-Delete.bru** - Verifies 401 error for unauthorized batch deletes

## Running the Tests

Run all job tests in sequence using Bruno. The tests are numbered to ensure proper execution order.

The batch operation tests (17, 30, 31) should run in sequence to:
1. Create test data
2. Update test data
3. Clean up test data

This ensures the database is left in a clean state after the tests complete.

