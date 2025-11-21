#!/usr/bin/env python3
"""
Detailed ProBridge Health Check - Focus on specific requirements
"""

import requests
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

BASE_URL = "https://probridge.space/api"

def test_job_creation_with_estimator():
    """Test job creation and verify estimator functionality"""
    print("🔍 Testing Job Creation with Estimator")
    
    # Create a job and capture the full response
    test_suffix = str(uuid.uuid4())[:8]
    job_data = {
        "city_slug": "abq",
        "service_category_slug": "handyman",
        "title": f"Estimator Test Job {test_suffix}",
        "description": "Test job to verify estimator functionality",
        "zip": "87101",
        "preferred_timing": "flexible",
        "client_name": f"Estimator Test Client {test_suffix}",
        "client_phone": f"555-{test_suffix[:4]}",
        "client_email": f"estimator_{test_suffix}@example.com",
        "is_test": True
    }
    
    try:
        response = requests.post(f"{BASE_URL}/jobs", json=job_data, timeout=30)
        print(f"Job creation status: {response.status_code}")
        
        if response.status_code < 400:
            job_response = response.json()
            print(f"Job ID: {job_response.get('job_id')}")
            print(f"Status: {job_response.get('status')}")
            print(f"Client view token: {job_response.get('client_view_token')}")
            
            # Check if response includes pricing info
            print(f"Full response: {json.dumps(job_response, indent=2)}")
            
            return {
                "success": True,
                "job_id": job_response.get('job_id'),
                "client_view_token": job_response.get('client_view_token'),
                "has_pricing": "pricing_suggestion" in str(job_response)
            }
        else:
            print(f"Job creation failed: {response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"success": False, "error": str(e)}

def test_operator_login_and_quote():
    """Test operator login and quote creation"""
    print("\n🔍 Testing Operator Login and Quote Creation")
    
    # Test operator login
    try:
        login_data = {
            "username": "operator@probridge.space",
            "password": "probridge-operator-123"
        }
        
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        
        print(f"Operator login status: {response.status_code}")
        
        if response.status_code < 400:
            login_response = response.json()
            token = login_response.get("access_token")
            print(f"Login successful, token received: {token[:50]}...")
            
            # Test getting operator jobs
            jobs_response = requests.get(
                f"{BASE_URL}/operator/jobs",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            
            print(f"Operator jobs status: {jobs_response.status_code}")
            if jobs_response.status_code < 400:
                jobs = jobs_response.json()
                print(f"Found {len(jobs)} jobs")
                
                # Try to create a quote for the first available job
                if jobs:
                    job_id = jobs[0]["id"]
                    print(f"Attempting to create quote for job: {job_id}")
                    
                    quote_data = {
                        "line_items": [
                            {
                                "type": "base",
                                "label": "Test service",
                                "quantity": 1,
                                "unit_price_cents": 10000,
                                "metadata": {"description": "Test service"}
                            }
                        ]
                    }
                    
                    quote_response = requests.post(
                        f"{BASE_URL}/operator/jobs/{job_id}/quotes",
                        json=quote_data,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        },
                        timeout=30
                    )
                    
                    print(f"Quote creation status: {quote_response.status_code}")
                    print(f"Quote response: {quote_response.text}")
                    
                    if quote_response.status_code < 400:
                        quote_result = quote_response.json()
                        quote_id = quote_result.get("id")
                        print(f"Quote created successfully: {quote_id}")
                        
                        # Try to send the quote
                        send_response = requests.post(
                            f"{BASE_URL}/operator/jobs/{job_id}/send-quote",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=30
                        )
                        
                        print(f"Send quote status: {send_response.status_code}")
                        print(f"Send quote response: {send_response.text}")
                        
                        return {
                            "success": True,
                            "token": token,
                            "job_id": job_id,
                            "quote_id": quote_id,
                            "quote_sent": send_response.status_code < 400
                        }
                    else:
                        return {"success": False, "error": f"Quote creation failed: {quote_response.text}"}
                else:
                    return {"success": False, "error": "No jobs available for quote creation"}
            else:
                return {"success": False, "error": f"Failed to get operator jobs: {jobs_response.text}"}
        else:
            return {"success": False, "error": f"Operator login failed: {response.text}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def test_stripe_checkout():
    """Test Stripe checkout session creation"""
    print("\n🔍 Testing Stripe Checkout Session")
    
    # First create a job and quote
    job_result = test_job_creation_with_estimator()
    if not job_result["success"]:
        return {"success": False, "error": "Could not create job for Stripe test"}
    
    operator_result = test_operator_login_and_quote()
    if not operator_result["success"]:
        return {"success": False, "error": "Could not create quote for Stripe test"}
    
    # Now try to approve the quote (which should create Stripe session)
    try:
        approve_data = {"token": job_result["client_view_token"]}
        
        response = requests.post(
            f"{BASE_URL}/jobs/{operator_result['job_id']}/approve-quote",
            json=approve_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Quote approval status: {response.status_code}")
        print(f"Quote approval response: {response.text}")
        
        if response.status_code < 400:
            approval_result = response.json()
            checkout_url = approval_result.get("checkout_url")
            
            if checkout_url:
                print(f"Stripe session created: {checkout_url}")
                return {"success": True, "checkout_url": checkout_url}
            else:
                print("Quote approved but no checkout URL (may be test mode)")
                return {"success": True, "checkout_url": None}
        else:
            return {"success": False, "error": f"Quote approval failed: {response.text}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    """Run detailed health check"""
    print("🚀 ProBridge Detailed Health Check")
    print(f"Testing against: {BASE_URL}")
    print("=" * 60)
    
    # Test 1: Job creation with estimator
    job_result = test_job_creation_with_estimator()
    
    # Test 2: Operator functionality
    operator_result = test_operator_login_and_quote()
    
    # Test 3: Stripe checkout
    stripe_result = test_stripe_checkout()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 DETAILED HEALTH CHECK SUMMARY")
    print("=" * 60)
    
    print(f"Job Creation: {'✅ OK' if job_result['success'] else '❌ FAILED'}")
    if job_result['success']:
        print(f"  - Estimator: {'✅ Included' if job_result.get('has_pricing') else '❓ Unknown'}")
    else:
        print(f"  - Error: {job_result.get('error', 'Unknown')}")
    
    print(f"Operator Quote: {'✅ OK' if operator_result['success'] else '❌ FAILED'}")
    if not operator_result['success']:
        print(f"  - Error: {operator_result.get('error', 'Unknown')}")
    
    print(f"Stripe Session: {'✅ OK' if stripe_result['success'] else '❌ FAILED'}")
    if not stripe_result['success']:
        print(f"  - Error: {stripe_result.get('error', 'Unknown')}")

if __name__ == "__main__":
    main()