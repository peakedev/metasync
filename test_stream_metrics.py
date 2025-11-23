#!/usr/bin/env python3
"""
Quick test script to verify stream processing metrics are working correctly.
This script makes a stream request and then retrieves it to check the metrics.
"""

import requests
import json
import time
import sys

# Configuration - update these
BASE_URL = "http://localhost:8000"  # or your API URL
CLIENT_ID = "d486037e-d1d7-4213-980e-0f47d8677ad2"  # from your env
CLIENT_API_KEY = "your-key-here"  # from your env
MODEL = "o4-mini"  # or your test model

def test_stream_metrics():
    """Test that stream processing metrics are captured correctly."""
    
    print("=" * 80)
    print("TESTING STREAM PROCESSING METRICS")
    print("=" * 80)
    
    # Step 1: Create a stream
    print("\n1. Creating stream request...")
    stream_url = f"{BASE_URL}/stream"
    headers = {
        "Content-Type": "application/json",
        "client_id": CLIENT_ID,
        "client_api_key": CLIENT_API_KEY
    }
    payload = {
        "userPrompt": "Tell me a short story",
        "model": MODEL,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(stream_url, headers=headers, json=payload, stream=True)
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"   ERROR: {response.text}")
            return False
        
        # Get stream ID from header
        stream_id = response.headers.get('X-Stream-Id') or response.headers.get('x-stream-id')
        print(f"   Stream ID: {stream_id}")
        
        # Consume the stream
        print("\n2. Consuming stream response...")
        full_text = ""
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                full_text += chunk
        
        print(f"   Received {len(full_text)} characters")
        print(f"   Preview: {full_text[:100]}...")
        
        # Wait a moment for the database to update
        print("\n3. Waiting 2 seconds for DB update...")
        time.sleep(2)
        
        # Step 2: Retrieve the stream and check metrics
        print("\n4. Retrieving stream to verify metrics...")
        get_url = f"{BASE_URL}/stream/{stream_id}"
        get_response = requests.get(get_url, headers=headers)
        print(f"   Status: {get_response.status_code}")
        
        if get_response.status_code != 200:
            print(f"   ERROR: {get_response.text}")
            return False
        
        stream_data = get_response.json()
        print("\n5. Checking processingMetrics...")
        
        # Verify processingMetrics exists
        if 'processingMetrics' not in stream_data:
            print("   ❌ FAIL: processingMetrics field missing!")
            return False
        
        metrics = stream_data['processingMetrics']
        print(f"\n   Processing Metrics:")
        print(f"   {json.dumps(metrics, indent=4)}")
        
        # Check required fields
        required_fields = ['inputTokens', 'outputTokens', 'totalTokens', 'duration']
        optional_fields = ['inputCost', 'outputCost', 'totalCost', 'currency']
        
        print("\n6. Validating required fields...")
        all_good = True
        
        for field in required_fields:
            if field not in metrics:
                print(f"   ❌ FAIL: Missing required field '{field}'")
                all_good = False
            else:
                value = metrics[field]
                print(f"   ✓ {field}: {value}")
                if value == 0 and field != 'duration':
                    print(f"      ⚠️  WARNING: {field} is 0 (should be > 0)")
        
        # Check optional cost fields
        print("\n7. Checking optional cost fields...")
        has_costs = 'inputCost' in metrics
        if has_costs:
            for field in optional_fields:
                if field not in metrics:
                    print(f"   ❌ FAIL: Missing cost field '{field}'")
                    all_good = False
                else:
                    value = metrics[field]
                    print(f"   ✓ {field}: {value}")
        else:
            print("   ℹ️  No cost fields (model may not have pricing configured)")
        
        # Verify totals
        print("\n8. Verifying calculations...")
        if 'totalTokens' in metrics and 'inputTokens' in metrics and 'outputTokens' in metrics:
            expected_total = metrics['inputTokens'] + metrics['outputTokens']
            if metrics['totalTokens'] == expected_total:
                print(f"   ✓ totalTokens matches: {metrics['totalTokens']} = {metrics['inputTokens']} + {metrics['outputTokens']}")
            else:
                print(f"   ❌ FAIL: totalTokens mismatch: {metrics['totalTokens']} != {expected_total}")
                all_good = False
        
        if has_costs and 'totalCost' in metrics and 'inputCost' in metrics and 'outputCost' in metrics:
            expected_cost = metrics['inputCost'] + metrics['outputCost']
            if abs(metrics['totalCost'] - expected_cost) < 0.0001:  # Float comparison
                print(f"   ✓ totalCost matches: {metrics['totalCost']:.6f} ≈ {expected_cost:.6f}")
            else:
                print(f"   ❌ FAIL: totalCost mismatch: {metrics['totalCost']} != {expected_cost}")
                all_good = False
        
        print("\n" + "=" * 80)
        if all_good:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED")
        print("=" * 80)
        
        return all_good
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\nMake sure to update the configuration at the top of this script!")
    print("BASE_URL, CLIENT_ID, CLIENT_API_KEY, and MODEL\n")
    
    input("Press Enter to continue...")
    
    success = test_stream_metrics()
    sys.exit(0 if success else 1)

