"""
Simulate the exact email from the screenshot to verify end-to-end logic
without touching real mailbox state.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from backend.email_monitor import extract_intel_with_claude, update_google_sheet, _open_sheet

# ─── Simulate the demo email from the screenshot ─────────────────────────────
fake_email = {
    "id": "SIMULATED-DONT-MARK",
    "subject": "RE: T1C-R01 / 3 Grazier Lane, Belconnen",
    "bodyPreview": "Hi Valentina, the expected net rental for 3 Grazier Lane is $67,500 per annum, and total outgoings are $10,231.39 p.a. Thanks, Ray White.",
    "receivedDateTime": "2026-05-21T09:30:00Z",
    "sender": {
        "emailAddress": {
            "address": "agent@raywhite.com",
            "name": "Ray White Agent"
        }
    }
}

subject      = fake_email["subject"]
body         = fake_email["bodyPreview"]
sender_email = fake_email["sender"]["emailAddress"]["address"]

print(f"Simulating email: '{subject}' from {sender_email}\n")

intel = extract_intel_with_claude(subject, body, sender_email)
print(f"Claude result: {intel}\n")

if intel and intel.get("is_property_email"):
    success = update_google_sheet(fake_email, intel, sender_email)
    print(f"\nSheet updated: {success}")
else:
    print("Claude says this is not a property email (unexpected).")
