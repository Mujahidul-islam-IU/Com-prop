import msal
import requests
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from config import AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, MONITOR_EMAIL

def get_recent_emails():
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET
    )
    result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        
    token = result.get("access_token")
    if not token:
        print("Failed to authenticate.")
        return

    # Fetch top 4 messages
    endpoint = f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}/mailFolders/inbox/messages?$top=4&$orderby=receivedDateTime desc"
    headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json'
    }
    
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        messages = response.json().get('value', [])
        for i, msg in enumerate(messages, 1):
            print(f"--- Email {i} ---")
            print(f"From: {msg.get('sender', {}).get('emailAddress', {}).get('name')} <{msg.get('sender', {}).get('emailAddress', {}).get('address')}>")
            print(f"Subject: {msg.get('subject')}")
            print(f"Date: {msg.get('receivedDateTime')}")
            print(f"Preview: {msg.get('bodyPreview')}\n")
    else:
        print(f"Error fetching emails: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    get_recent_emails()
