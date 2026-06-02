import os, sys, gspread
from oauth2client.service_account import ServiceAccountCredentials

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.config import GOOGLE_SHEETS_CREDENTIALS_FILE

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
g_client = gspread.authorize(creds)

sheet = g_client.open("property list").sheet1
headers = sheet.row_values(1)
print("Headers:", headers)
print()
records = sheet.get_all_records()
print(f"Total data rows: {len(records)}")
if records:
    print("First row:")
    for k, v in records[0].items():
        print(f"  [{k}] = {repr(v)}")
