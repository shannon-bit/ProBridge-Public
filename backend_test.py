#!/usr/bin/env python3
"""
ProBridge Backend Smoke Testing
Focus on: (1) basic startup sanity, (2) offline payment money loop
Tests: create job -> operator sends quote -> client approves -> offline payment transitions
"""

import requests
import json
import uuid
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Use local backend for smoke testing (since we're testing the running instance)
BASE_URL = "http://localhost:8001/api"
print(f"Using local backend URL: {BASE_URL}")

class ProBridgeTestClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
    def test_endpoint(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Test an API endpoint and return structured result"""
        url = f"{BASE_URL}{endpoint}"
        
        try:
            if headers:
                test_headers = {**self.session.headers, **headers}
            else:
                test_headers = self.session.headers
                
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, headers=test_headers, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data, params=params, headers=test_headers, timeout=30)
            elif method.upper() == 'PATCH':
                response = self.session.patch(url, json=data, params=params, headers=test_headers, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
                
            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "data": response.json() if response.content else {},
                "error": None if response.status_code < 400 else f"HTTP {response.status_code}: {response.text[:200]}"
            }
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON decode error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    def test_endpoint_form(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                          headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Test an API endpoint with form data and return structured result"""
        url = f"{BASE_URL}{endpoint}"
        
        try:
            # Create a new session for form data to avoid JSON headers
            form_session = requests.Session()
            if headers:
                form_session.headers.update(headers)
                
            if method.upper() == 'POST':
                response = form_session.post(url, data=data, params=params, timeout=30)
            else:
                return {"success": False, "error": f"Form method only supports POST"}
                
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

def test_basic_startup_sanity():
    """Test basic startup sanity - FastAPI app imports correctly, no Stripe env required"""
    client = ProBridgeTestClient()
    test_results = []
    
    print("🔍 Testing Basic Startup Sanity")
    print("=" * 40)
    
    # Test root endpoint
    root_result = client.test_endpoint('GET', '/')
    test_results.append(("GET / (root)", root_result))
    
    if root_result["success"]:
        print("✅ Root endpoint accessible - FastAPI app started correctly")
        print(f"   Response: {root_result['data']}")
    else:
        print(f"❌ Root endpoint failed: {root_result['error']}")
    
    # Test meta endpoints (should work without auth)
    cities_result = client.test_endpoint('GET', '/meta/cities')
    test_results.append(("GET /meta/cities", cities_result))
    
    if cities_result["success"]:
        print("✅ Cities endpoint working - basic DB connectivity OK")
        cities = cities_result["data"]
        print(f"   Found {len(cities)} cities")
    else:
        print(f"❌ Cities endpoint failed: {cities_result['error']}")
    
    categories_result = client.test_endpoint('GET', '/meta/service-categories')
    test_results.append(("GET /meta/service-categories", categories_result))
    
    if categories_result["success"]:
        print("✅ Service categories endpoint working")
        categories = categories_result["data"]
        print(f"   Found {len(categories)} service categories")
    else:
        print(f"❌ Service categories endpoint failed: {categories_result['error']}")
    
    return test_results

def test_offline_payment_money_loop():
    """Test offline payment money loop: create job -> operator quote -> client approve -> offline payment"""
    client = ProBridgeTestClient()
    test_results = []
    
    print("\n💰 Testing Offline Payment Money Loop")
    print("=" * 50)
    
    # Test data
    test_suffix = str(uuid.uuid4())[:8]
    client_email = f"smokeclient_{test_suffix}@example.com"
    
    # Store test state
    test_state = {
        "job_id": None,
        "client_view_token": None,
        "operator_token": None,
        "quote_id": None
    }
    
    # Step 1: Create a client job
    print("\n👤 Step 1: Client Job Creation")
    
    job_data = {
        "city_slug": "abq",
        "service_category_slug": "handyman", 
        "title": f"Smoke Test Job {test_suffix}",
        "description": "Smoke test for offline payment flow - fix kitchen sink",
        "zip": "87101",
        "preferred_timing": "this_week",
        "client_name": f"Smoke Client {test_suffix}",
        "client_phone": f"505-{test_suffix[:4]}",
        "client_email": client_email,
        "is_test": True
    }
    
    job_result = client.test_endpoint('POST', '/jobs', job_data)
    test_results.append(("POST /jobs", job_result))
    
    if job_result["success"]:
        print("✅ Job creation successful")
        test_state["job_id"] = job_result["data"]["job_id"]
        test_state["client_view_token"] = job_result["data"]["client_view_token"]
        print(f"   Job ID: {test_state['job_id']}")
        print(f"   Status: {job_result['data']['status']}")
    else:
        print(f"❌ Job creation failed: {job_result['error']}")
        return test_results
    
    # Step 2: Operator login (use pre-seeded operator)
    print("\n👨‍💼 Step 2: Operator Login")
    
    # Use the pre-seeded operator from server.py: operator@probridge.space / probridge-operator-123
    operator_login_result = client.test_endpoint_form('POST', '/auth/login', {
        "username": "operator@probridge.space",
        "password": "probridge-operator-123"
    })
    test_results.append(("POST /auth/login (operator)", operator_login_result))
    
    if operator_login_result["success"]:
        print("✅ Operator login successful")
        test_state["operator_token"] = operator_login_result["data"]["access_token"]
    else:
        print(f"❌ Operator login failed: {operator_login_result['error']}")
        print("   Trying to continue without operator authentication...")
        # Continue without operator token for now
    
    # Step 3: Create and send quote
    print("\n💰 Step 3: Create Quote")
    
    if test_state["job_id"]:
        # Try without auth first to see the error
        quote_data = {
            "line_items": [
                {
                    "type": "base",
                    "label": "Kitchen sink repair",
                    "quantity": 1,
                    "unit_price_cents": 15000,
                    "metadata": {"description": "Fix kitchen sink - smoke test"}
                }
            ]
        }
        
        if test_state.get("operator_token"):
            auth_headers = {"Authorization": f"Bearer {test_state['operator_token']}"}
        else:
            auth_headers = {}
            
        quote_result = client.test_endpoint('POST', f'/operator/jobs/{test_state["job_id"]}/quotes', 
                                          quote_data, headers=auth_headers)
        test_results.append(("POST /operator/jobs/{job_id}/quotes", quote_result))
        
        if quote_result["success"]:
            print("✅ Quote creation successful")
            test_state["quote_id"] = quote_result["data"]["id"]
            print(f"   Quote ID: {test_state['quote_id']}")
            print(f"   Total: ${quote_result['data']['total_price_cents'] / 100:.2f}")
        else:
            print(f"❌ Quote creation failed: {quote_result['error']}")
            print("   This is expected without operator authentication")
    
    # Step 4: Send quote to client
    print("\n📤 Step 4: Send Quote")
    
    if test_state["job_id"]:
        if test_state.get("operator_token"):
            auth_headers = {"Authorization": f"Bearer {test_state['operator_token']}"}
        else:
            auth_headers = {}
            
        send_quote_result = client.test_endpoint('POST', f'/operator/jobs/{test_state["job_id"]}/send-quote',
                                               headers=auth_headers)
        test_results.append(("POST /operator/jobs/{job_id}/send-quote", send_quote_result))
        
        if send_quote_result["success"]:
            print("✅ Quote sending successful")
        else:
            print(f"❌ Quote sending failed: {send_quote_result['error']}")
            print("   This is expected without operator authentication")
    
    # Step 5: Client approves quote (triggers offline payment)
    print("\n✅ Step 5: Client Approves Quote (Offline Payment)")
    
    if test_state["job_id"] and test_state["client_view_token"]:
        approve_data = {"token": test_state["client_view_token"]}
        approve_result = client.test_endpoint('POST', f'/jobs/{test_state["job_id"]}/approve-quote', approve_data)
        test_results.append(("POST /jobs/{job_id}/approve-quote", approve_result))
        
        if approve_result["success"]:
            print("✅ Quote approval successful")
            print(f"   Payment mode: {approve_result['data'].get('payment_mode', 'N/A')}")
            print(f"   New status: {approve_result['data']['status']}")
            
            # Should transition to awaiting_payment for offline mode
            if approve_result['data']['status'] == 'awaiting_payment':
                print("✅ Job correctly transitioned to awaiting_payment")
            else:
                print(f"⚠️  Expected awaiting_payment, got {approve_result['data']['status']}")
        else:
            print(f"❌ Quote approval failed: {approve_result['error']}")
            return test_results
    
    # Step 6: Operator marks payment as received
    print("\n💳 Step 6: Operator Marks Payment Received")
    
    if test_state["job_id"]:
        if test_state.get("operator_token"):
            auth_headers = {"Authorization": f"Bearer {test_state['operator_token']}"}
        else:
            auth_headers = {}
            
        mark_paid_result = client.test_endpoint('POST', f'/operator/jobs/{test_state["job_id"]}/mark-payment-received',
                                              headers=auth_headers)
        test_results.append(("POST /operator/jobs/{job_id}/mark-payment-received", mark_paid_result))
        
        if mark_paid_result["success"]:
            print("✅ Payment marking successful")
            print(f"   Payment status: {mark_paid_result['data'].get('status', 'N/A')}")
        else:
            print(f"❌ Payment marking failed: {mark_paid_result['error']}")
            print("   This is expected without operator authentication")
    
    # Step 7: Final status check
    print("\n🔍 Step 7: Final Job Status Check")
    
    if test_state["job_id"] and test_state["client_view_token"]:
        final_status_result = client.test_endpoint('GET', f'/jobs/{test_state["job_id"]}/status',
                                                 params={"token": test_state["client_view_token"]})
        test_results.append(("Final GET /jobs/{job_id}/status", final_status_result))
        
        if final_status_result["success"]:
            print("✅ Final job status check successful")
            final_status = final_status_result['data']['status']
            print(f"   Final status: {final_status}")
            
            # Should be 'confirmed' after payment received
            if final_status == 'confirmed':
                print("✅ Offline payment flow completed successfully")
            else:
                print(f"⚠️  Expected 'confirmed' status, got '{final_status}'")
                
            quote_total = final_status_result['data'].get('quote_total_cents')
            if quote_total is not None:
                print(f"   Quote total: ${quote_total / 100:.2f}")
        else:
            print(f"❌ Final job status check failed: {final_status_result['error']}")
    
    return test_results

def print_test_summary(test_results):
    """Print a summary of all test results"""
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
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
    
    print("\n✅ PASSED TESTS:")
    for test_name, result in test_results:
        if result["success"]:
            print(f"   • {test_name}")

if __name__ == "__main__":
    try:
        print("🚀 ProBridge Backend Smoke Test")
        print(f"Testing against: {BASE_URL}")
        print("=" * 60)
        
        # Test 1: Basic startup sanity
        startup_results = test_basic_startup_sanity()
        
        # Test 2: Offline payment money loop
        money_loop_results = test_offline_payment_money_loop()
        
        # Combine results
        all_results = startup_results + money_loop_results
        
        print_test_summary(all_results)
        
    except Exception as e:
        print(f"\n💥 Test execution failed: {str(e)}")
        import traceback
        traceback.print_exc()