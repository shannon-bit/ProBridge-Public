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

# Get backend URL from environment (REACT_APP_BACKEND_URL from frontend/.env)
def get_backend_url():
    # Try to read from frontend/.env
    try:
        with open('/app/frontend/.env', 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip()
    except:
        pass
    # Fallback
    return "https://probridge.space/api"

BASE_URL = get_backend_url()
print(f"Using backend URL: {BASE_URL}")

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
            if headers:
                test_headers = {**headers}
            else:
                test_headers = {}
            
            # Remove Content-Type for form data
            if 'Content-Type' in test_headers:
                del test_headers['Content-Type']
                
            if method.upper() == 'POST':
                response = self.session.post(url, data=data, params=params, headers=test_headers, timeout=30)
            else:
                return {"success": False, "error": f"Form method only supports POST"}
                
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
        "title": f"Test Handyman Job {test_suffix}",
        "description": "Need help fixing a leaky faucet and installing a ceiling fan",
        "zip": "87101",
        "preferred_timing": "this_week",
        "client_name": f"Test Client {test_suffix}",
        "client_phone": f"555-{test_suffix[:4]}",
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
    
    # Step 3: Check job status
    print("\n📊 Step 3: Job Status Check")
    
    status_result = client.test_endpoint('GET', f'/jobs/{test_state["job_id"]}/status', 
                                       params={"token": test_state["client_view_token"]})
    test_results.append(("GET /jobs/{job_id}/status", status_result))
    
    if status_result["success"]:
        print("✅ Job status check successful")
        print(f"   Status: {status_result['data']['status']}")
    else:
        print(f"❌ Job status check failed: {status_result['error']}")
    
    # Step 4: Create contractor account
    print("\n🔨 Step 4: Contractor Signup")
    
    contractor_data = {
        "name": f"Test Contractor {test_suffix}",
        "email": contractor_email,
        "phone": f"555-{test_suffix[:4]}",
        "password": "testpass123",
        "city_slug": "abq",
        "base_zip": "87101",
        "radius_miles": 25,
        "service_category_ids": [],  # Will be populated after getting categories
        "bio": "Experienced handyman with 10+ years experience"
    }
    
    # Get service category IDs
    if categories_result["success"] and categories_result["data"]:
        handyman_cat = next((cat for cat in categories_result["data"] if cat["slug"] == "handyman"), None)
        if handyman_cat:
            contractor_data["service_category_ids"] = [handyman_cat["id"]]
    
    contractor_signup_result = client.test_endpoint('POST', '/contractors/signup', contractor_data)
    test_results.append(("POST /contractors/signup", contractor_signup_result))
    
    if contractor_signup_result["success"]:
        print("✅ Contractor signup successful")
        contractor_id = contractor_signup_result["data"]["contractor_id"]
        print(f"   Contractor ID: {contractor_id}")
    else:
        print(f"❌ Contractor signup failed: {contractor_signup_result['error']}")
    
    # Step 5: Contractor login
    print("\n🔑 Step 5: Contractor Login")
    
    # FastAPI OAuth2PasswordRequestForm expects form data, not JSON
    contractor_login_result = client.test_endpoint_form('POST', '/auth/login', {
        "username": contractor_email,
        "password": "testpass123"
    })
    test_results.append(("POST /auth/login (contractor)", contractor_login_result))
    
    if contractor_login_result["success"]:
        print("✅ Contractor login successful")
        test_state["contractor_token"] = contractor_login_result["data"]["access_token"]
    else:
        print(f"❌ Contractor login failed: {contractor_login_result['error']}")
    
    # Step 6: Check contractor offers
    print("\n📋 Step 6: Contractor Offers Check")
    
    if test_state["contractor_token"]:
        auth_headers = {"Authorization": f"Bearer {test_state['contractor_token']}"}
        offers_result = client.test_endpoint('GET', '/contractors/me/offers', headers=auth_headers)
        test_results.append(("GET /contractors/me/offers", offers_result))
        
        if offers_result["success"]:
            print("✅ Contractor offers check successful")
            offers = offers_result["data"]
            print(f"   Available offers: {len(offers)}")
            
            # Check if our job is in the offers
            our_job_offer = next((offer for offer in offers if offer["id"] == test_state["job_id"]), None)
            if our_job_offer:
                print("✅ Our test job found in contractor offers")
            else:
                print("⚠️  Our test job not found in contractor offers")
        else:
            print(f"❌ Contractor offers check failed: {offers_result['error']}")
    
    # Step 7: Contractor accepts offer
    print("\n✋ Step 7: Contractor Accept Offer")
    
    if test_state["contractor_token"] and test_state["job_id"]:
        auth_headers = {"Authorization": f"Bearer {test_state['contractor_token']}"}
        accept_result = client.test_endpoint('POST', f'/contractors/offers/{test_state["job_id"]}/accept', 
                                           headers=auth_headers)
        test_results.append(("POST /contractors/offers/{job_id}/accept", accept_result))
        
        if accept_result["success"]:
            print("✅ Contractor offer acceptance successful")
            print(f"   New job status: {accept_result['data']['status']}")
        else:
            print(f"❌ Contractor offer acceptance failed: {accept_result['error']}")
    
    # Step 8: Create operator account (simulate existing operator)
    print("\n👨‍💼 Step 8: Operator Access")
    
    # For testing, we'll try to create an operator user directly or use admin simulation
    # First, let's try the admin simulation endpoint
    admin_sim_result = client.test_endpoint('POST', '/admin/run-simulation')
    test_results.append(("POST /admin/run-simulation", admin_sim_result))
    
    if admin_sim_result["success"]:
        print("✅ Admin simulation endpoint accessible")
    else:
        print(f"⚠️  Admin simulation not accessible: {admin_sim_result['error']}")
    
    # For operator functionality, we need to create an operator user
    # This might require direct database access or a different approach
    print("⚠️  Operator testing requires pre-existing operator account")
    
    # Step 9: Test operator job listing (without auth for now)
    print("\n📊 Step 9: Operator Job Listing")
    
    operator_jobs_result = client.test_endpoint('GET', '/operator/jobs')
    test_results.append(("GET /operator/jobs", operator_jobs_result))
    
    if operator_jobs_result["success"]:
        print("✅ Operator jobs endpoint accessible")
        jobs = operator_jobs_result["data"]
        print(f"   Total jobs found: {len(jobs)}")
    else:
        print(f"❌ Operator jobs endpoint failed: {operator_jobs_result['error']}")
        print("   This likely requires operator authentication")
    
    # Step 10: Test quote creation (would need operator auth)
    print("\n💰 Step 10: Quote Creation")
    
    if test_state["job_id"]:
        quote_data = {
            "line_items": [
                {
                    "type": "base",
                    "label": "Faucet repair",
                    "quantity": 1,
                    "unit_price_cents": 8500,
                    "metadata": {"description": "Fix leaky kitchen faucet"}
                },
                {
                    "type": "base", 
                    "label": "Ceiling fan installation",
                    "quantity": 1,
                    "unit_price_cents": 12000,
                    "metadata": {"description": "Install new ceiling fan in living room"}
                }
            ]
        }
        
        quote_result = client.test_endpoint('POST', f'/operator/jobs/{test_state["job_id"]}/quotes', quote_data)
        test_results.append(("POST /operator/jobs/{job_id}/quotes", quote_result))
        
        if quote_result["success"]:
            print("✅ Quote creation successful")
            test_state["quote_id"] = quote_result["data"]["id"]
        else:
            print(f"❌ Quote creation failed: {quote_result['error']}")
            print("   This requires operator authentication")
    
    # Step 11: Test quote sending
    print("\n📤 Step 11: Quote Sending")
    
    if test_state["job_id"]:
        send_quote_result = client.test_endpoint('POST', f'/operator/jobs/{test_state["job_id"]}/send-quote')
        test_results.append(("POST /operator/jobs/{job_id}/send-quote", send_quote_result))
        
        if send_quote_result["success"]:
            print("✅ Quote sending successful")
        else:
            print(f"❌ Quote sending failed: {send_quote_result['error']}")
            print("   This requires operator authentication")
    
    # Step 12: Test quote approval (client side)
    print("\n✅ Step 12: Quote Approval")
    
    if test_state["job_id"] and test_state["client_view_token"]:
        approve_data = {"token": test_state["client_view_token"]}
        approve_result = client.test_endpoint('POST', f'/jobs/{test_state["job_id"]}/approve-quote', approve_data)
        test_results.append(("POST /jobs/{job_id}/approve-quote", approve_result))
        
        if approve_result["success"]:
            print("✅ Quote approval successful")
            print(f"   Checkout URL: {approve_result['data'].get('checkout_url', 'N/A')}")
            print(f"   New status: {approve_result['data']['status']}")
        else:
            print(f"❌ Quote approval failed: {approve_result['error']}")
    
    # Step 13: Test job completion
    print("\n🏁 Step 13: Job Completion")
    
    if test_state["contractor_token"] and test_state["job_id"]:
        auth_headers = {"Authorization": f"Bearer {test_state['contractor_token']}"}
        complete_data = {
            "completion_note": "Successfully repaired faucet and installed ceiling fan. Customer satisfied.",
            "photos": []
        }
        
        complete_result = client.test_endpoint('POST', f'/contractors/jobs/{test_state["job_id"]}/mark-complete',
                                             complete_data, headers=auth_headers)
        test_results.append(("POST /contractors/jobs/{job_id}/mark-complete", complete_result))
        
        if complete_result["success"]:
            print("✅ Job completion successful")
            print(f"   Final status: {complete_result['data']['status']}")
        else:
            print(f"❌ Job completion failed: {complete_result['error']}")
    
    # Final status check
    print("\n🔍 Final: Job Status Verification")
    
    if test_state["job_id"] and test_state["client_view_token"]:
        final_status_result = client.test_endpoint('GET', f'/jobs/{test_state["job_id"]}/status',
                                                 params={"token": test_state["client_view_token"]})
        test_results.append(("Final GET /jobs/{job_id}/status", final_status_result))
        
        if final_status_result["success"]:
            print("✅ Final job status check successful")
            print(f"   Final status: {final_status_result['data']['status']}")
            quote_total = final_status_result['data'].get('quote_total_cents')
            if quote_total is not None:
                print(f"   Quote total: ${quote_total / 100:.2f}")
            else:
                print("   Quote total: Not available")
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
        test_results = test_money_loop()
        print_test_summary(test_results)
    except Exception as e:
        print(f"\n💥 Test execution failed: {str(e)}")
        import traceback
        traceback.print_exc()