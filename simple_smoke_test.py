#!/usr/bin/env python3
"""
Simple ProBridge Backend Smoke Test
Focus on basic functionality and identify critical issues
"""

import requests
import json
import uuid
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8001/api"

def test_endpoint(method: str, endpoint: str, data: Optional[Dict] = None, 
                 headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Test an API endpoint and return structured result"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        session = requests.Session()
        if headers:
            session.headers.update(headers)
        else:
            session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            })
            
        if method.upper() == 'GET':
            response = session.get(url, params=params, timeout=30)
        elif method.upper() == 'POST':
            response = session.post(url, json=data, params=params, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}
            
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "data": response.json() if response.content else {},
            "error": None if response.status_code < 400 else f"HTTP {response.status_code}: {response.text[:500]}"
        }
        
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON decode error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}

def test_form_endpoint(method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
    """Test form data endpoint"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        session = requests.Session()
        response = session.post(url, data=data, timeout=30)
        
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "data": response.json() if response.content else {},
            "error": None if response.status_code < 400 else f"HTTP {response.status_code}: {response.text[:500]}"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error: {str(e)}"}

def main():
    print("🔍 ProBridge Backend Simple Smoke Test")
    print(f"Testing: {BASE_URL}")
    print("=" * 50)
    
    test_results = []
    
    # Test 1: Basic startup
    print("\n1. Basic Startup Test")
    root_result = test_endpoint('GET', '/')
    test_results.append(("Root endpoint", root_result))
    
    if root_result["success"]:
        print("✅ FastAPI app started correctly")
        print(f"   Response: {root_result['data']}")
    else:
        print(f"❌ Root endpoint failed: {root_result['error']}")
        return
    
    # Test 2: Database connectivity
    print("\n2. Database Connectivity Test")
    cities_result = test_endpoint('GET', '/meta/cities')
    test_results.append(("Cities endpoint", cities_result))
    
    if cities_result["success"]:
        print("✅ Database connectivity OK")
        print(f"   Found {len(cities_result['data'])} cities")
    else:
        print(f"❌ Database connectivity failed: {cities_result['error']}")
    
    categories_result = test_endpoint('GET', '/meta/service-categories')
    test_results.append(("Service categories", categories_result))
    
    if categories_result["success"]:
        print("✅ Service categories working")
        print(f"   Found {len(categories_result['data'])} categories")
    else:
        print(f"❌ Service categories failed: {categories_result['error']}")
    
    # Test 3: Job creation (core functionality)
    print("\n3. Job Creation Test")
    test_suffix = str(uuid.uuid4())[:8]
    job_data = {
        "city_slug": "abq",
        "service_category_slug": "handyman", 
        "title": f"Simple Smoke Test {test_suffix}",
        "description": "Basic smoke test job creation",
        "zip": "87101",
        "preferred_timing": "flexible",
        "client_name": f"Test Client {test_suffix}",
        "client_phone": f"505-{test_suffix[:4]}",
        "client_email": f"test_{test_suffix}@example.com",
        "is_test": True
    }
    
    job_result = test_endpoint('POST', '/jobs', job_data)
    test_results.append(("Job creation", job_result))
    
    if job_result["success"]:
        print("✅ Job creation successful")
        job_id = job_result["data"]["job_id"]
        client_token = job_result["data"]["client_view_token"]
        print(f"   Job ID: {job_id}")
        print(f"   Status: {job_result['data']['status']}")
        
        # Test 4: Job status check
        print("\n4. Job Status Check")
        status_result = test_endpoint('GET', f'/jobs/{job_id}/status', 
                                    params={"token": client_token})
        test_results.append(("Job status", status_result))
        
        if status_result["success"]:
            print("✅ Job status check successful")
            print(f"   Status: {status_result['data']['status']}")
        else:
            print(f"❌ Job status check failed: {status_result['error']}")
    else:
        print(f"❌ Job creation failed: {job_result['error']}")
    
    # Test 5: Authentication test
    print("\n5. Authentication Test")
    auth_result = test_form_endpoint('POST', '/auth/login', {
        "username": "testoperator@example.com",
        "password": "testpass123"
    })
    test_results.append(("Operator login", auth_result))
    
    if auth_result["success"]:
        print("✅ Authentication working")
        token = auth_result["data"]["access_token"]
        print(f"   Token received: {token[:20]}...")
    else:
        print(f"❌ Authentication failed: {auth_result['error']}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SMOKE TEST SUMMARY")
    print("=" * 50)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for _, result in test_results if result["success"])
    failed_tests = total_tests - passed_tests
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {failed_tests} ❌")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests > 0:
        print("\n❌ FAILED TESTS:")
        for test_name, result in test_results:
            if not result["success"]:
                print(f"   • {test_name}: {result['error']}")
    
    # Critical issues check
    critical_issues = []
    if not any(name == "Root endpoint" and result["success"] for name, result in test_results):
        critical_issues.append("FastAPI app not starting properly")
    if not any(name == "Cities endpoint" and result["success"] for name, result in test_results):
        critical_issues.append("Database connectivity issues")
    if not any(name == "Job creation" and result["success"] for name, result in test_results):
        critical_issues.append("Core job creation functionality broken")
    
    if critical_issues:
        print("\n🚨 CRITICAL ISSUES FOUND:")
        for issue in critical_issues:
            print(f"   • {issue}")
    else:
        print("\n✅ No critical issues found - basic backend functionality working")

if __name__ == "__main__":
    main()