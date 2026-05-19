# ============================================================
#  commercialrealestate.com.au Scraper — Configuration File
# ============================================================
# SETUP: Copy this file to config.py and fill in your values.
#   cp config.example.py config.py
# ============================================================

# --- Search Parameters ---
LOCATION = "Melbourne Region VIC"       # e.g. "Melbourne CBD VIC", "Brisbane QLD"
KEYWORD  = "office"                     # e.g. "Warehouse", "Retail", "Factory", ""
MIN_SIZE = 210                          # Floor area in m² (0 = no minimum)
LISTING_TYPE = "for-lease"              # "for-sale" | "for-lease" | "sold" | "leased"

# --- Scraping Behaviour ---
MAX_PAGES    = 1                        # How many pages of results to scrape
FETCH_DETAILS = True                    # Also visit each listing's detail page?

# --- Output ---
OUTPUT_DIR = "./output"                 # Where to save JSON + CSV files

# --- Phase 2: Enquiry & LLM Configuration ---
# Get your Anthropic API key at: https://console.anthropic.com/
ANTHROPIC_API_KEY = "sk-ant-..."

# Google Sheets service account JSON (place the file in this directory)
GOOGLE_SHEETS_CREDENTIALS_FILE = "service_account.json"
GOOGLE_SHEET_NAME = "Property Enquiries"

# Your real contact details (used to fill the enquiry form)
ENQUIRY_NAME  = "Your Name"
ENQUIRY_EMAIL = "youremail@example.com"    # Use your real email so agents can reply!
ENQUIRY_PHONE = "0400000000"

# Claude Prompt Configuration
CLAUDE_PROMPT_CRITERIA = """
You are an expert commercial real estate analyst. 
Analyze the following property description and identify if it has:
- Good potential for high yield.
- Suitable zoning for warehouse/industrial use.
- High clearance ceilings.
Based on this, draft a professional, short, and highly specific enquiry message to the agent asking 1-2 relevant questions.
Return ONLY the message you want to send to the agent, nothing else.
"""

# --- Phase 3: Email Reply Monitor (Coming Soon) ---
# Azure App Registration credentials (portal.azure.com)
AZURE_TENANT_ID     = "your-azure-tenant-id"
AZURE_CLIENT_ID     = "your-azure-client-id"
AZURE_CLIENT_SECRET = "your-azure-client-secret"
MONITOR_EMAIL       = "youremail@example.com"
POLL_INTERVAL_MINS  = 15

# --- Anti-Detection ---
# The scraper uses a persistent browser profile stored at:
#   ~/.cre_scraper_profile_uc
# On first run, Cloudflare may show a challenge. The browser will open
# visibly — just wait (it usually auto-solves within ~10 seconds).
