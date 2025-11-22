#!/usr/bin/env python3
"""
Test operator endpoints specifically to identify ObjectId serialization issues
"""

import requests
import json

BASE_URL = "http://localhost:8001/api"

def test_with_auth():
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
    print(f"✅ Got operator token: {token[:20]}...")
    
    # Set auth header
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    
    # Test operator/jobs endpoint
    print("\n🔍 Testing operator/jobs endpoint...")
    jobs_response = session.get(f"{BASE_URL}/operator/jobs")
    
    print(f"Status: {jobs_response.status_code}")
    if jobs_response.status_code == 200:
        try:
            jobs_data = jobs_response.json()
            print(f"✅ Jobs endpoint working - found {len(jobs_data)} jobs")
            if jobs_data:
                print(f"   Sample job keys: {list(jobs_data[0].keys())}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"   Raw response: {jobs_response.text[:200]}")
    else:
        print(f"❌ Jobs endpoint failed: {jobs_response.text}")
    
    # Test operator/contractors endpoint
    print("\n🔍 Testing operator/contractors endpoint...")
    contractors_response = session.get(f"{BASE_URL}/operator/contractors")
    
    print(f"Status: {contractors_response.status_code}")
    if contractors_response.status_code == 200:
        try:
            contractors_data = contractors_response.json()
            print(f"✅ Contractors endpoint working - found {len(contractors_data)} contractors")
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"   Raw response: {contractors_response.text[:200]}")
    else:
        print(f"❌ Contractors endpoint failed: {contractors_response.text}")

if __name__ == "__main__":
    test_with_auth()