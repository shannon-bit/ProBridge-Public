#!/usr/bin/env python3
"""
Test quote creation specifically to identify the ObjectId issue
"""

import requests
import json

BASE_URL = "http://localhost:8001/api"

def test_quote_creation():
    # Get operator token
    session = requests.Session()
    
    # Login as operator
    login_response = session.post(f"{BASE_URL}/auth/login", data={
        "username": "testoperator@example.com",
        "password": "testpass123"
    })
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print(f"✅ Got operator token")
    
    # Set auth header
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    
    # Get a job to create quote for
    jobs_response = session.get(f"{BASE_URL}/operator/jobs")
    if jobs_response.status_code != 200:
        print("❌ Can't get jobs")
        return
    
    jobs = jobs_response.json()
    if not jobs:
        print("❌ No jobs found")
        return
    
    job_id = jobs[0]["id"]
    print(f"✅ Using job ID: {job_id}")
    print(f"   Job status: {jobs[0]['status']}")
    
    # Test quote creation
    print("\n🔍 Testing quote creation...")
    quote_data = {
        "line_items": [
            {
                "type": "base",
                "label": "Test service",
                "quantity": 1,
                "unit_price_cents": 10000,
                "metadata": {"description": "Test quote"}
            }
        ]
    }
    
    quote_response = session.post(f"{BASE_URL}/operator/jobs/{job_id}/quotes", json=quote_data)
    
    print(f"Status: {quote_response.status_code}")
    print(f"Response headers: {dict(quote_response.headers)}")
    
    if quote_response.status_code == 200:
        try:
            quote_result = quote_response.json()
            print(f"✅ Quote creation successful")
            print(f"   Quote ID: {quote_result.get('id')}")
            print(f"   Total: ${quote_result.get('total_price_cents', 0) / 100:.2f}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"   Raw response: {quote_response.text}")
    else:
        print(f"❌ Quote creation failed")
        print(f"   Response: {quote_response.text}")
        
    # Check backend logs for any errors
    print(f"\n📋 Response content length: {len(quote_response.content)}")
    if quote_response.content:
        print(f"   First 200 chars: {quote_response.text[:200]}")

if __name__ == "__main__":
    test_quote_creation()