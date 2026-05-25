"""
Email Reply Monitor
===================
Reads unread emails from the monitored mailbox via Microsoft Graph API,
uses Claude to detect property-related replies, extracts financial data
(purchase price, outgoings, net rent) with per-sqm vs annual detection,
matches the property address against the Google Sheet, and writes to the
correct columns based on what the agent quoted.
"""
import json
import re
import difflib
import sys
import os

import requests
import msal
import gspread

# Allow running directly as `python backend/email_monitor.py`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oauth2client.service_account import ServiceAccountCredentials
from anthropic import Anthropic

from config import (
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, MONITOR_EMAIL,
    ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEET_NAME,
    COL_PURCHASE_PRICE, COL_OUTGOINGS_PA, COL_OUTGOINGS_PER_SQM,
    COL_NET_RENTAL_PA, COL_NET_RENTAL_PER_SQM,
)

# -------------------------------------------------------
#  Client initialisation
# -------------------------------------------------------

try:
    claude = Anthropic(api_key=ANTHROPIC_API_KEY)
except Exception as e:
    print(f"[ERROR] Anthropic init failed: {e}")
    claude = None


def _open_sheet():
    """Open and return the Google Sheet (sheet1). Raises on failure."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_SHEETS_CREDENTIALS_FILE, scope
    )
    gc = gspread.authorize(creds)
    return gc.open(GOOGLE_SHEET_NAME).sheet1


try:
    sheet = _open_sheet()
    print(f"[INFO] Google Sheet '{GOOGLE_SHEET_NAME}' opened successfully.")
except Exception as e:
    print(f"[ERROR] Google Sheets init failed: {e}")
    sheet = None


# -------------------------------------------------------
#  Microsoft Graph helpers
# -------------------------------------------------------

def get_graph_token():
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_silent(
        ["https://graph.microsoft.com/.default"], account=None
    )
    if not result:
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
    return result.get("access_token")


def fetch_unread_emails(token):
    """Fetch up to 25 unread emails from the inbox."""
    endpoint = (
        f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}"
        f"/mailFolders/inbox/messages"
        f"?$filter=isRead eq false&$top=25"
        f"&$select=id,subject,sender,receivedDateTime,bodyPreview,body"
    )
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = requests.get(endpoint, headers=headers, timeout=15)
    if resp.status_code == 200:
        return resp.json().get("value", [])
    print(f"[ERROR] Graph fetch failed: {resp.status_code} - {resp.text[:200]}")
    return []


def fetch_full_body(token, message_id):
    """Fetch the full plain-text body of a single message."""
    endpoint = (
        f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}"
        f"/messages/{message_id}"
        f"?$select=body"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Prefer": 'outlook.body-content-type="text"',
    }
    resp = requests.get(endpoint, headers=headers, timeout=15)
    if resp.status_code == 200:
        return resp.json().get("body", {}).get("content", "")
    return ""


def mark_email_read(token, email_id):
    """Mark an email as read and tag it as processed."""
    endpoint = (
        f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}"
        f"/messages/{email_id}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    requests.patch(
        endpoint,
        headers=headers,
        json={"isRead": True, "categories": ["Agent Reply - Processed"]},
        timeout=10,
    )


# -------------------------------------------------------
#  Claude extraction
# -------------------------------------------------------

EXTRACTION_PROMPT = """You are an expert commercial real estate analyst.

Read the following email from a property agent replying to our enquiry.
We asked them for: asking price, indicative net rent per sqm, and total annual outgoings.

Analyse the email and extract the following data. Return ONLY a valid JSON object.

Rules:
1. "is_property_email" - Is this a reply about a real estate property? (true/false)
2. "property_address" - The property address (look in the subject line first, then body). null if not found.
3. "agent_email" - The agent's email address (use sender unless body specifies another). null if not found.
4. "purchase_price" - The asking/purchase price quoted (e.g. "$610,000", "$1.2M"). null if not mentioned.
5. "outgoings_value" - The outgoings amount the agent quoted (just the number/amount, e.g. "$15,000" or "$45"). null if not mentioned.
6. "outgoings_is_per_sqm" - true if the agent explicitly said outgoings are "per sqm" or "per m2". false if they said it as an annual/total amount. false if not mentioned.
7. "net_rent_value" - The net rent amount the agent quoted (e.g. "$250" or "$120,000"). null if not mentioned.
8. "net_rent_is_per_sqm" - true if the agent explicitly said the net rent is "per sqm" or "per m2". false if they said it as an annual/total amount. false if not mentioned.

IMPORTANT: Look carefully for keywords like "per sqm", "per m2", "/sqm", "/m2", "psm" to determine if a figure is per-square-metre.
If the agent just says a total annual amount without mentioning "per sqm", set the _is_per_sqm flag to false.

Return ONLY valid JSON:
{{
  "is_property_email": <true|false>,
  "property_address": "<string or null>",
  "agent_email": "<string or null>",
  "purchase_price": "<string or null>",
  "outgoings_value": "<string or null>",
  "outgoings_is_per_sqm": <true|false>,
  "net_rent_value": "<string or null>",
  "net_rent_is_per_sqm": <true|false>
}}

Email Subject: {subject}
Sender Email: {sender_email}
Email Body:
{body}
"""


def extract_intel_with_claude(subject, body, sender_email):
    """
    Ask Claude to analyse the agent's email reply and return structured JSON
    with purchase price, outgoings, net rent, and per-sqm flags.
    """
    if not claude:
        return None

    prompt = EXTRACTION_PROMPT.format(
        subject=subject,
        sender_email=sender_email,
        body=body[:3000],
    )

    try:
        resp = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if Claude adds them
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [ERROR] Claude extraction failed: {e}")
        return None


# -------------------------------------------------------
#  Address matching helpers
# -------------------------------------------------------

def _normalize(text):
    """Lowercase, strip punctuation/special chars, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(text).lower())).strip()


def _keyword_overlap(query, candidate):
    """
    Fraction of significant words (>3 chars) in `candidate` that appear in `query`.
    Returns 0.0-1.0.
    """
    q_words = set(query.split())
    c_words = {w for w in candidate.split() if len(w) > 3}
    if not c_words:
        return 0.0
    return len(q_words & c_words) / len(c_words)


def find_matching_row(records, intel, email_subject, sender_email):
    """
    Try three strategies to find the Google Sheet row (1-indexed) that matches
    the email.  Returns -1 if no match is found.

    Strategy 1 - Exact sender email matches agent_mail column.
    Strategy 2 - Keyword overlap between (subject + extracted address) and address column.
    Strategy 3 - difflib fuzzy match on the extracted address.
    """
    norm_sender = _normalize(sender_email)
    extracted_address = _normalize(intel.get("property_address") or "")
    search_text = _normalize(email_subject) + " " + extracted_address

    # Strategy 1: exact agent email
    for idx, row in enumerate(records):
        stored_mail = _normalize(row.get("agent_mail", ""))
        if stored_mail and stored_mail != "none" and stored_mail == norm_sender:
            print(f"  -> [Match] agent email at row {idx + 2}")
            return idx + 2

    # Strategy 2: keyword overlap on address
    best_score, best_idx = 0.0, -1
    norm_addresses = [_normalize(r.get("address", "")) for r in records]

    for idx, norm_addr in enumerate(norm_addresses):
        if not norm_addr or norm_addr == "none":
            continue
        score = _keyword_overlap(search_text, norm_addr)
        if score > best_score:
            best_score, best_idx = score, idx

    if best_score >= 0.55 and best_idx != -1:
        print(
            f"  -> [Match] keyword overlap {best_score:.0%} at row {best_idx + 2} "
            f"(address: {records[best_idx].get('address', '')})"
        )
        return best_idx + 2

    # Strategy 3: difflib fuzzy on extracted address
    if extracted_address:
        close = difflib.get_close_matches(
            extracted_address, norm_addresses, n=1, cutoff=0.45
        )
        if close:
            idx = norm_addresses.index(close[0])
            print(
                f"  -> [Match] difflib fuzzy at row {idx + 2} "
                f"(address: {records[idx].get('address', '')})"
            )
            return idx + 2

    print("  -> No matching row found in Google Sheet.")
    return -1


# -------------------------------------------------------
#  Google Sheet update
# -------------------------------------------------------

def _ensure_columns_exist(headers):
    """Add any missing financial columns to the sheet header row."""
    new_cols = [
        COL_PURCHASE_PRICE,
        COL_OUTGOINGS_PA,
        COL_OUTGOINGS_PER_SQM,
        COL_NET_RENTAL_PA,
        COL_NET_RENTAL_PER_SQM,
    ]
    changed = False
    for col in new_cols:
        if col not in headers:
            headers.append(col)
            col_letter = gspread.utils.rowcol_to_a1(1, len(headers))
            sheet.update(range_name=col_letter, values=[[col]])
            print(f"  -> Added new column: '{col}'")
            changed = True
    return headers


def update_google_sheet(email, intel, sender_email):
    """
    Match the email to a sheet row and write financial data to the
    correct columns based on per-sqm vs annual detection.

    Column routing:
      - Purchase Price           -> always COL_PURCHASE_PRICE
      - Outgoings (is_per_sqm)   -> COL_OUTGOINGS_PER_SQM
      - Outgoings (annual)       -> COL_OUTGOINGS_PA
      - Net Rent (is_per_sqm)    -> COL_NET_RENTAL_PER_SQM
      - Net Rent (annual)        -> COL_NET_RENTAL_PA
      - Agent email              -> agent_mail column
    """
    if not sheet:
        print("  [WARN] Google Sheet not available, skipping update.")
        return False

    all_records = sheet.get_all_records()
    headers = sheet.row_values(1)

    # Ensure new financial columns exist
    headers = _ensure_columns_exist(headers)

    subject = email.get("subject", "")
    match_row = find_matching_row(all_records, intel, subject, sender_email)
    if match_row == -1:
        return False

    # Build update map: column_name -> value
    updates = {}

    # Agent email
    agent_email = (intel.get("agent_email") or sender_email or "").strip()
    if agent_email:
        updates["agent_mail"] = agent_email

    # Purchase Price
    purchase_price = (intel.get("purchase_price") or "").strip()
    if purchase_price:
        updates[COL_PURCHASE_PRICE] = purchase_price

    # Outgoings routing
    outgoings = (intel.get("outgoings_value") or "").strip()
    if outgoings:
        if intel.get("outgoings_is_per_sqm"):
            updates[COL_OUTGOINGS_PER_SQM] = outgoings
        else:
            updates[COL_OUTGOINGS_PA] = outgoings

    # Net Rent routing
    net_rent = (intel.get("net_rent_value") or "").strip()
    if net_rent:
        if intel.get("net_rent_is_per_sqm"):
            updates[COL_NET_RENTAL_PER_SQM] = net_rent
        else:
            updates[COL_NET_RENTAL_PA] = net_rent

    if not updates:
        print("  [WARN] Nothing to update (no financial data or agent email extracted).")
        return False

    for col_name, val in updates.items():
        if col_name not in headers:
            print(f"  [WARN] Column '{col_name}' not found in sheet, skipping.")
            continue
        col_idx = headers.index(col_name) + 1
        sheet.update_cell(match_row, col_idx, str(val))
        print(f"  -> Updated [{col_name}] = {val!r}")

    return True


# -------------------------------------------------------
#  Main entry point
# -------------------------------------------------------

def run_monitor():
    """
    Fetch unread emails, analyse each with Claude, and update the Google Sheet
    for any that are property-related agent replies.
    """
    print("\n[INFO] -- Email Monitor starting --")
    token = get_graph_token()
    if not token:
        print("[ERROR] Failed to obtain Graph API token.")
        return {"status": "error", "message": "Graph auth failed"}

    emails = fetch_unread_emails(token)
    print(f"[INFO] {len(emails)} unread email(s) found.")

    processed = 0
    skipped = 0

    for email in emails:
        subject = email.get("subject", "(no subject)")
        preview = email.get("bodyPreview", "")
        sender_email = (
            email.get("sender", {})
                 .get("emailAddress", {})
                 .get("address", "")
        )

        print(f"\n-- Processing: '{subject}' | from: {sender_email}")

        # Fetch the full body for better extraction accuracy
        full_body = fetch_full_body(token, email["id"]) or preview

        intel = extract_intel_with_claude(subject, full_body, sender_email)
        if not intel:
            print("  -> Skipping (Claude extraction failed).")
            skipped += 1
            continue

        print(f"  -> Claude result: {json.dumps(intel)}")

        if not intel.get("is_property_email"):
            print("  -> Not a property email, skipping.")
            skipped += 1
            continue

        success = update_google_sheet(email, intel, sender_email)
        if success:
            mark_email_read(token, email["id"])
            processed += 1
        else:
            skipped += 1

    summary = {
        "status": "success",
        "processed": processed,
        "skipped": skipped,
        "total": len(emails),
    }
    print(f"\n[INFO] Done. {processed} updated, {skipped} skipped out of {len(emails)} total.")
    return summary


if __name__ == "__main__":
    run_monitor()
