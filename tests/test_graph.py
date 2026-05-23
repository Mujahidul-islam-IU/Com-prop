import msal
import requests
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from config import AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, MONITOR_EMAIL

def test_connection():
    print(f"Testing Microsoft Graph Connection for {MONITOR_EMAIL}...")
    
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET
    )
    
    result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
    if not result:
        print("No suitable token exists in cache. Let's get a new one from AAD.")
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        
    if "access_token" in result:
        print("[SUCCESS] Successfully acquired Access Token.")
        
        # Test fetching emails
        endpoint = f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}/mailFolders/inbox/messages?$top=3"
        headers = {
            'Authorization': 'Bearer ' + result['access_token'],
            'Accept': 'application/json'
        }
        
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            print("[SUCCESS] Successfully connected to Inbox.")
            data = response.json()
            messages = data.get('value', [])
            print(f"Found {len(messages)} recent messages.")
            for msg in messages:
                print(f" - Subject: {msg.get('subject')}")
                print(f"   From: {msg.get('sender', {}).get('emailAddress', {}).get('address')}")
        else:
            print(f"[ERROR] Failed to fetch emails. Status: {response.status_code}")
            print(response.text)
    else:
        print("[ERROR] Failed to acquire token.")
        print(result.get("error"))
        print(result.get("error_description"))
        print(result.get("correlation_id"))

if __name__ == "__main__":
    test_connection()
