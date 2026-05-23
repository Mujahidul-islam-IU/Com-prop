import time
import requests
import msal
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from anthropic import Anthropic
import sys
import re

from config import (
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, MONITOR_EMAIL,
    ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEET_NAME
)

# Initialize Anthropic Client
try:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
except Exception as e:
    print(f"[ERROR] Failed to initialize Anthropic client: {e}")
    client = None

# Initialize Google Sheets Client
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
    g_client = gspread.authorize(creds)
    sheet = g_client.open(GOOGLE_SHEET_NAME).sheet1
except Exception as e:
    print(f"[ERROR] Failed to initialize Google Sheets client: {e}")
    sheet = None

def get_graph_token():
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET
    )
    result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

def fetch_unread_emails(token):
    # Fetch unread emails from Inbox
    endpoint = f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}/mailFolders/inbox/messages?$filter=isRead eq false&$top=20"
    headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json'
    }
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        return response.json().get('value', [])
    else:
        print(f"[ERROR] Failed to fetch emails: {response.status_code}")
        return []

def mark_email_read(token, email_id):
    endpoint = f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}/messages/{email_id}"
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    payload = {
        "isRead": True,
        "categories": ["Agent Reply - Processed"]
    }
    requests.patch(endpoint, headers=headers, json=payload)

def extract_intel_with_claude(subject, body, size_sqm):
    prompt = f"""You are an expert commercial real estate analyst. 
Read the following email from a property agent and extract key data.

The property is {size_sqm} sqm.

Calculate the monthly price per sqm (Market Sqm Rent) based on the size provided.
Identify if it is For Sale or For Lease.

Return your analysis strictly as a JSON object with the following keys:
- "property_id": (string or null, if mentioned in subject or body)
- "classification": (string: "Positive", "Negative", "Price Quote", "Info Request", or "Other")
- "summary": (string: 1-sentence summary of the reply)
- "sale_or_lease": (string: "Sale" or "Lease")
- "required_purchase_price": (string or null, the total price quoted for sale or lease, e.g. "$650,000" or "$120,000 pa")
- "market_sqm_rent": (string or null, calculated monthly price per sqm based on the size {size_sqm}, e.g. "$28.50")

Email Subject: {subject}
Email Body:
{body}

Output ONLY valid JSON.
"""
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_output = response.content[0].text
        # Clean up JSON if Claude wraps it in markdown
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_output:
            raw_output = raw_output.split("```")[1].strip()
            
        return json.loads(raw_output)
    except Exception as e:
        print(f"[ERROR] Claude extraction failed: {e}")
        return None

def update_google_sheet(email, intel):
    if not sheet:
        return False
        
    all_records = sheet.get_all_records()
    headers = sheet.row_values(1)
    
    # Ensure new columns exist
    new_cols = ["Reply Received", "Reply Date", "Reply From", "Reply Classification", "Reply Summary", "Required Purchase Price", "Market Sqm Rent"]
    for col in new_cols:
        if col not in headers:
            headers.append(col)
            sheet.update(range_name=f"{gspread.utils.rowcol_to_a1(1, len(headers))}", values=[[col]])
    
    sender_email = email.get('sender', {}).get('emailAddress', {}).get('address', '')
    
    # Find matching row
    match_row_idx = -1
    property_size = "Unknown"
    
    email_subject = str(email.get('subject', '')).lower()
    
    for idx, row in enumerate(all_records):
        # 1. Match by Property ID (if available)
        pid = str(row.get('PID') or '').strip()
        if intel.get('property_id') and str(intel['property_id']) in pid and pid and pid.lower() != 'none':
            match_row_idx = idx + 2 # +2 because 1-indexed and header row
            property_size = str(row.get('size') or '')
            break
        
        # 2. Match by Agent Email
        agent_mail = str(row.get('agent_mail') or '').strip().lower()
        if sender_email and agent_mail and agent_mail != 'none' and sender_email.lower() == agent_mail:
            match_row_idx = idx + 2
            property_size = str(row.get('size') or '')
            break
            
        # 3. Match by Property Address in Subject
        address = str(row.get('address') or '').strip().lower()
        if address and address != 'none' and address in email_subject:
            match_row_idx = idx + 2
            property_size = str(row.get('size') or '')
            break
            
        # 4. Match by Title in Subject
        title = str(row.get('title') or '').strip().lower()
        if title and title != 'none' and title in email_subject:
            match_row_idx = idx + 2
            property_size = str(row.get('size') or '')
            break
            
    if match_row_idx != -1:
        # Update row
        print(f"  -> Matched row {match_row_idx} (Size: {property_size})")
        
        # Re-run intel extraction with correct size if it was "Unknown" initially
        if property_size != "Unknown":
            # We already ran it with "Unknown" size, let's run it again with real size for math
            intel_recalc = extract_intel_with_claude(email.get('subject', ''), email.get('bodyPreview', ''), property_size)
            if intel_recalc:
                intel = intel_recalc
                
        # Fill data
        reply_data = {
            "Reply Received": "TRUE",
            "Reply Date": email.get('receivedDateTime', '').split('T')[0],
            "Reply From": sender_email,
            "Reply Classification": intel.get('classification', ''),
            "Reply Summary": intel.get('summary', ''),
            "Required Purchase Price": intel.get('required_purchase_price', ''),
            "Market Sqm Rent": intel.get('market_sqm_rent', '')
        }
        
        for col_name, val in reply_data.items():
            col_idx = headers.index(col_name) + 1
            sheet.update_cell(match_row_idx, col_idx, str(val))
            
        return True
        
    print("  -> No matching row found in Google Sheet.")
    return False


def run_monitor():
    print("[INFO] Starting Email Monitor...")
    token = get_graph_token()
    if not token:
        print("[ERROR] Failed to get Graph token.")
        return {"status": "error", "message": "Auth failed"}
        
    emails = fetch_unread_emails(token)
    print(f"[INFO] Found {len(emails)} unread emails.")
    
    processed_count = 0
    for email in emails:
        subject = email.get('subject', '')
        body = email.get('bodyPreview', '')
        print(f"\nProcessing: {subject}")
        
        intel = extract_intel_with_claude(subject, body, "Unknown")
        if intel:
            print(f"  -> Claude extracted: {json.dumps(intel)}")
            success = update_google_sheet(email, intel)
            if success:
                mark_email_read(token, email.get('id'))
                processed_count += 1
                
    print(f"\n[INFO] Monitor finished. Processed {processed_count} emails.")
    return {"status": "success", "processed": processed_count}

if __name__ == "__main__":
    run_monitor()
