#!/bin/bash

# Comprehensive test script for Clients API endpoints
# Usage: ./test_clients.sh [TARGET_HOST] [ADMIN_API_KEY]
# Example: ./test_clients.sh
# Example: ./test_clients.sh http://localhost:8001
# Example: ./test_clients.sh http://localhost:8001 myadminkey

# Set default values
DEFAULT_HOST="http://localhost:8001"
DEFAULT_ADMIN_API_KEY="test_admin_key"

# Use provided values or defaults
BASE_URL="${1:-$DEFAULT_HOST}"
ADMIN_API_KEY="${2:-$DEFAULT_ADMIN_API_KEY}"

echo "🧪 Testing Clients API endpoints with full CRUD cycle..."
CLEANUP_IDS=()

# Function to cleanup created resources
cleanup() {
    echo ""
    echo "🧹 Cleaning up created resources..."
    for id in "${CLEANUP_IDS[@]}"; do
        if [ -n "$id" ] && [ "$id" != "null" ]; then
            echo "  Deleting client: $id"
            curl -s -X DELETE "$BASE_URL/clients/$id" \
              -H "Content-Type: application/json" \
              -H "admin_api_key: $ADMIN_API_KEY" > /dev/null
        fi
    done
    echo "✅ Cleanup completed"
}

# Set trap to cleanup on exit
trap cleanup EXIT

echo ""
echo "1. Testing GET /clients (list all clients)"
CLIENT_COUNT=$(curl -s "$BASE_URL/clients" -H "admin_api_key: $ADMIN_API_KEY" | jq 'length')
echo "✅ Found $CLIENT_COUNT clients"

echo ""
echo "2. Testing POST /clients (create new client)"
NEW_CLIENT=$(curl -s -X POST "$BASE_URL/clients" \
  -H "Content-Type: application/json" \
  -H "admin_api_key: $ADMIN_API_KEY" \
  -d '{
    "name": "Test Client from Shell"
  }')

CLIENT_ID=$(echo "$NEW_CLIENT" | jq -r '.clientId')
CLIENT_API_KEY=$(echo "$NEW_CLIENT" | jq -r '.api_key')
if [ "$CLIENT_ID" != "null" ] && [ -n "$CLIENT_ID" ]; then
    CLEANUP_IDS+=("$CLIENT_ID")
    echo "✅ Created client with ID: $CLIENT_ID"
    echo "   API Key (first 8 chars): ${CLIENT_API_KEY:0:8}..."
    
    echo ""
    echo "3. Testing GET /clients/{id} (get by ID)"
    CLIENT_DOC=$(curl -s "$BASE_URL/clients/$CLIENT_ID" -H "admin_api_key: $ADMIN_API_KEY")
    CLIENT_NAME=$(echo "$CLIENT_DOC" | jq -r '.name')
    echo "✅ Retrieved client: $CLIENT_NAME"
    
    # Verify client structure
    echo ""
    echo "3.1. Testing client structure"
    HAS_CLIENT_ID=$(echo "$CLIENT_DOC" | jq 'has("clientId")')
    HAS_NAME=$(echo "$CLIENT_DOC" | jq 'has("name")')
    HAS_ENABLED=$(echo "$CLIENT_DOC" | jq 'has("enabled")')
    HAS_CREATED_AT=$(echo "$CLIENT_DOC" | jq 'has("created_at")')
    NO_API_KEY=$(echo "$CLIENT_DOC" | jq 'has("api_key") | not')
    
    if [ "$HAS_CLIENT_ID" = "true" ] && [ "$HAS_NAME" = "true" ] && [ "$HAS_ENABLED" = "true" ] && [ "$HAS_CREATED_AT" = "true" ] && [ "$NO_API_KEY" = "true" ]; then
        echo "✅ All required fields present and API key excluded"
    else
        echo "❌ Missing required fields or API key exposed"
        exit 1
    fi
    
    echo ""
    echo "4. Testing PATCH /clients/{id} (update client)"
    UPDATED_CLIENT=$(curl -s -X PATCH "$BASE_URL/clients/$CLIENT_ID" \
      -H "Content-Type: application/json" \
      -H "admin_api_key: $ADMIN_API_KEY" \
      -d '{
        "name": "Updated Client Name",
        "enabled": false
      }')
    
    UPDATED_NAME=$(echo "$UPDATED_CLIENT" | jq -r '.name')
    UPDATED_ENABLED=$(echo "$UPDATED_CLIENT" | jq -r '.enabled')
    if [ "$UPDATED_NAME" = "Updated Client Name" ] && [ "$UPDATED_ENABLED" = "false" ]; then
        echo "✅ Client updated successfully"
    else
        echo "❌ Client update failed"
        exit 1
    fi
    
    echo ""
    echo "5. Testing POST /clients/{id}/toggle (toggle enabled status)"
    TOGGLED_CLIENT=$(curl -s -X POST "$BASE_URL/clients/$CLIENT_ID/toggle" \
      -H "Content-Type: application/json" \
      -H "admin_api_key: $ADMIN_API_KEY")
    
    TOGGLED_ENABLED=$(echo "$TOGGLED_CLIENT" | jq -r '.enabled')
    if [ "$TOGGLED_ENABLED" = "true" ]; then
        echo "✅ Client enabled status toggled to: $TOGGLED_ENABLED"
    else
        echo "❌ Toggle failed"
        exit 1
    fi
    
    echo ""
    echo "6. Testing POST /clients/{id}/rotate-key (rotate API key)"
    ROTATED_CLIENT=$(curl -s -X POST "$BASE_URL/clients/$CLIENT_ID/rotate-key" \
      -H "Content-Type: application/json" \
      -H "admin_api_key: $ADMIN_API_KEY")
    
    NEW_API_KEY=$(echo "$ROTATED_CLIENT" | jq -r '.api_key')
    if [ "$NEW_API_KEY" != "null" ] && [ -n "$NEW_API_KEY" ] && [ ${#NEW_API_KEY} -eq 64 ]; then
        echo "✅ API key rotated successfully"
        echo "   New API Key (first 8 chars): ${NEW_API_KEY:0:8}..."
        if [ "$NEW_API_KEY" != "$CLIENT_API_KEY" ]; then
            echo "✅ New API key is different from original"
        else
            echo "❌ New API key matches original (should be different)"
            exit 1
        fi
    else
        echo "❌ Key rotation failed"
        exit 1
    fi
    
    echo ""
    echo "7. Testing DELETE /clients/{id} (delete client)"
    DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/clients/$CLIENT_ID" \
      -H "Content-Type: application/json" \
      -H "admin_api_key: $ADMIN_API_KEY")
    
    if [ "$DELETE_STATUS" = "204" ]; then
        echo "✅ Client deleted successfully"
        # Remove from cleanup list since it's already deleted
        CLEANUP_IDS=("${CLEANUP_IDS[@]/$CLIENT_ID}")
    else
        echo "❌ Delete failed with status: $DELETE_STATUS"
        exit 1
    fi
    
    echo ""
    echo "8. Testing GET /clients/{id} after deletion (should return 404)"
    DELETED_CLIENT=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/clients/$CLIENT_ID" \
      -H "admin_api_key: $ADMIN_API_KEY")
    
    if [ "$DELETED_CLIENT" = "404" ]; then
        echo "✅ Deleted client correctly returns 404"
    else
        echo "❌ Expected 404, got: $DELETED_CLIENT"
        exit 1
    fi
    
else
    echo "❌ Failed to create client"
    exit 1
fi

echo ""
echo "9. Testing error cases"
echo "9.1. Testing without admin API key (should return 401)"
UNAUTHORIZED_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/clients")
if [ "$UNAUTHORIZED_STATUS" = "401" ]; then
    echo "✅ Unauthorized request correctly returns 401"
else
    echo "❌ Expected 401, got: $UNAUTHORIZED_STATUS"
fi

echo ""
echo "9.2. Testing with invalid admin API key (should return 401)"
INVALID_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/clients" \
  -H "admin_api_key: invalid_key")
if [ "$INVALID_STATUS" = "401" ]; then
    echo "✅ Invalid API key correctly returns 401"
else
    echo "❌ Expected 401, got: $INVALID_STATUS"
fi

echo ""
echo "9.3. Testing GET non-existent client (should return 404)"
NOT_FOUND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/clients/non-existent-id" \
  -H "admin_api_key: $ADMIN_API_KEY")
if [ "$NOT_FOUND_STATUS" = "404" ]; then
    echo "✅ Non-existent client correctly returns 404"
else
    echo "❌ Expected 404, got: $NOT_FOUND_STATUS"
fi

echo ""
echo "✅ All tests completed successfully!"



