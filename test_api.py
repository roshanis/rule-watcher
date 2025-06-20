#!/usr/bin/env python3
"""
Test script for Federal Register API with healthcare-specific filtering
"""

import requests
import json

# Healthcare-related agencies from Federal Register API schemas
HEALTHCARE_AGENCIES = [
    "centers-for-medicare-medicaid-services",  # CMS - primary target
    "centers-for-disease-control-and-prevention",  # CDC
    "food-and-drug-administration",  # FDA
    "health-and-human-services-department",  # HHS
    "national-institutes-of-health",  # NIH
    "agency-for-healthcare-research-and-quality",  # AHRQ
    "health-resources-and-services-administration",  # HRSA
    "indian-health-service",  # IHS
    "substance-abuse-and-mental-health-services-administration",  # SAMHSA
    "medicare-payment-advisory-commission",  # MedPAC
    "reagan-udall-foundation-for-the-food-and-drug-administration",  # Reagan-Udall Foundation
]

API_BASE = "https://www.federalregister.gov/api/v1/documents.json"

def test_healthcare_agency_search():
    """Test healthcare agency filtering"""
    print("🏥 Testing Healthcare Agency Search")
    print("=" * 50)
    
    params = {
        "conditions[term]": "medicare medicaid healthcare health insurance medical hospital physician",
        "order": "newest",
        "per_page": 10,
        "page": 1
    }
    
    # Add multiple healthcare agency filters
    for i, agency in enumerate(HEALTHCARE_AGENCIES):
        params[f"conditions[agencies][{i}]"] = agency
    
    try:
        print(f"📡 Making API request with {len(HEALTHCARE_AGENCIES)} healthcare agencies...")
        print(f"🔍 Search query: {params['conditions[term]']}")
        
        response = requests.get(API_BASE, params=params, timeout=30)
        print(f"📊 Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            count = data.get("count", 0)
            
            print(f"📄 Found {len(results)} documents (total: {count})")
            
            if results:
                print("\n📋 Sample documents:")
                for i, doc in enumerate(results[:3]):
                    print(f"\n{i+1}. {doc.get('title', 'No title')[:100]}...")
                    print(f"   📅 Published: {doc.get('publication_date', 'Unknown')}")
                    print(f"   🏛️  Agencies: {', '.join(doc.get('agency_names', []))}")
                    print(f"   📄 Type: {doc.get('type', 'Unknown')}")
                    if doc.get('abstract'):
                        print(f"   📝 Abstract: {doc.get('abstract', '')[:150]}...")
            else:
                print("❌ No documents returned")
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

def test_cms_only_search():
    """Test CMS-only search for comparison"""
    print("\n🏥 Testing CMS-Only Search (for comparison)")
    print("=" * 50)
    
    params = {
        "conditions[term]": "medicare medicaid",
        "conditions[agencies][0]": "centers-for-medicare-medicaid-services",
        "order": "newest", 
        "per_page": 10,
        "page": 1
    }
    
    try:
        print("📡 Making CMS-only API request...")
        response = requests.get(API_BASE, params=params, timeout=30)
        print(f"📊 Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            count = data.get("count", 0)
            
            print(f"📄 Found {len(results)} CMS documents (total: {count})")
            
            if results:
                print(f"\n📋 First CMS document:")
                doc = results[0]
                print(f"   📋 Title: {doc.get('title', 'No title')}")
                print(f"   📅 Published: {doc.get('publication_date', 'Unknown')}")
                print(f"   🏛️  Agencies: {', '.join(doc.get('agency_names', []))}")
        else:
            print(f"❌ API Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_healthcare_agency_search()
    test_cms_only_search()
    print("\n✅ Testing complete!") 