import requests

# Test 1: Homepage
r = requests.get("http://127.0.0.1:8001/")
print(f"[TEST 1] Homepage: Status {r.status_code}")
print(f"  Has Reply Monitor section: {'reply-section' in r.text}")
print(f"  Has Scrape form: {'scrape-form' in r.text}")
print(f"  HTML length: {len(r.text)} chars")

# Test 2: Recent Emails API
r2 = requests.get("http://127.0.0.1:8001/api/recent-emails")
data = r2.json()
print(f"\n[TEST 2] Recent Emails API: Status {r2.status_code}")
print(f"  Response status: {data.get('status')}")
print(f"  Unread count: {data.get('count', 'N/A')}")
if data.get("emails"):
    for e in data["emails"]:
        print(f"  - {e.get('from')}: {e.get('subject')}")

# Test 3: Scrape endpoint exists
r3 = requests.options("http://127.0.0.1:8001/api/scrape")
print(f"\n[TEST 3] Scrape endpoint: Status {r3.status_code}")

# Test 4: Check-replies endpoint exists
r4 = requests.options("http://127.0.0.1:8001/api/check-replies")
print(f"\n[TEST 4] Check-replies endpoint: Status {r4.status_code}")

print("\n=== ALL TESTS COMPLETE ===")
