import os
import json
import time
import random
from typing import Dict, Optional
from selenium.webdriver.common.action_chains import ActionChains

# Phase 2 Dependencies
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    from anthropic import Anthropic
except ImportError:
    print("  [WARN] Missing Phase 2 dependencies. Run: pip install gspread oauth2client anthropic")

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import configs
from config import (
    ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEET_NAME,
    ENQUIRY_NAME, ENQUIRY_EMAIL, ENQUIRY_PHONE, CLAUDE_PROMPT_CRITERIA
)

def human_delay(min_ms: int = 800, max_ms: int = 2500):
    """Random pause in a human-plausible range."""
    time.sleep(random.uniform(min_ms / 1000.0, max_ms / 1000.0))


def human_type(element, text: str, wpm_range=(35, 75), allow_typos: bool = True):
    """Type text character-by-character with a realistic WPM speed and
    occasional typo-then-backspace correction to simulate human imperfection.

    Args:
        allow_typos: Set to False for sensitive fields (e.g. email) where
                     a failed backspace correction would corrupt the value.
    """
    from selenium.webdriver.common.keys import Keys

    # Convert WPM to per-character delay (avg 5 chars per word)
    wpm = random.uniform(*wpm_range)
    base_delay = 60.0 / (wpm * 5)  # seconds per character

    typo_pool = "qwertyuiopasdfghjklzxcvbnm"  # keys near real ones
    for i, char in enumerate(text):
        # ~5% chance of a typo on any character (only when allowed)
        if allow_typos and random.random() < 0.05 and len(text) > 4:
            wrong = random.choice(typo_pool)
            element.send_keys(wrong)
            time.sleep(random.uniform(0.15, 0.30))  # pause before noticing mistake
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.25, 0.45))  # longer correction pause for DOM to update

        element.send_keys(char)
        # Variable keystroke delay with occasional micro-pauses (thinking)
        delay = base_delay * random.uniform(0.5, 2.2)
        if random.random() < 0.08:          # ~8% chance of a longer hesitation
            delay += random.uniform(0.15, 0.6)
        time.sleep(delay)


def human_mouse_move_to(driver, element):
    """Move the mouse in a slightly random arc toward an element before clicking."""
    try:
        actions = ActionChains(driver)
        # Small random offset so the cursor doesn't always hit the exact center
        offset_x = random.randint(-8, 8)
        offset_y = random.randint(-4, 4)
        actions.move_to_element_with_offset(element, offset_x, offset_y)
        actions.perform()
        time.sleep(random.uniform(0.05, 0.18))  # tiny settle time
    except Exception:
        pass  # non-fatal; fall back to direct interaction


def human_scroll_and_read(driver, scroll_steps=None):
    """Scroll the page in a few small steps with pauses, as if reading content."""
    if scroll_steps is None:
        scroll_steps = random.randint(3, 6)
    for _ in range(scroll_steps):
        scroll_px = random.randint(200, 500)
        driver.execute_script(f"window.scrollBy(0, {scroll_px});")
        time.sleep(random.uniform(0.4, 1.2))
    # Occasionally scroll back up a little (re-reading behaviour)
    if random.random() < 0.3:
        driver.execute_script(f"window.scrollBy(0, -{random.randint(80, 200)});")
        time.sleep(random.uniform(0.3, 0.8))

class EnquiryAgent:
    def __init__(self):
        self.sheet = None
        self.anthropic_client = None
        
        self._init_google_sheets()
        self._init_anthropic()

    def _init_google_sheets(self):
        try:
            if not os.path.exists(GOOGLE_SHEETS_CREDENTIALS_FILE):
                print(f"  [WARN] Google Sheets credentials not found at {GOOGLE_SHEETS_CREDENTIALS_FILE}")
                return

            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
            client = gspread.authorize(creds)
            # Use the specific sheet ID provided by the user
            self.sheet = client.open_by_key("1KfDrhJewwuX0zWzATj1a1zP-g2nWuzWTvkchCcqmiYw").sheet1
            print("  [OK] Connected to Google Sheets.")
        except Exception as e:
            print(f"  [ERROR] Failed to connect to Google Sheets: {e}")

    def _init_anthropic(self):
        if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "sk-ant-...":
            try:
                self.anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
                print("  [OK] Connected to Anthropic (Claude) API.")
            except Exception as e:
                print(f"  [ERROR] Failed to initialize Anthropic client: {e}")
        else:
            print("  [WARN] Anthropic API Key not set. Skipping LLM integration.")

    def get_claude_enquiry_message(self, property_description: str) -> str:
        """Uses Claude to generate a custom enquiry message based on the description."""
        if not self.anthropic_client:
            return "Hi, I am interested in this property. Could you please send me more details?"

        print("  [LLM] Generating custom enquiry message via Claude...")
        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=300,
                temperature=0.7,
                system=CLAUDE_PROMPT_CRITERIA,
                messages=[
                    {
                        "role": "user",
                        "content": f"Here is the property description:\n\n{property_description}"
                    }
                ]
            )
            # Assuming response.content[0].text is the message
            msg = response.content[0].text.strip()
            print(f"  [LLM] Generated message: {msg[:100]}...")
            return msg
        except Exception as e:
            err_str = str(e)
            if "credit balance" in err_str or "credit_balance" in err_str:
                print(f"  [ERROR] Anthropic API credits exhausted. Disabling Claude for this session.")
                print(f"  [INFO]  Please top up credits at: https://console.anthropic.com/settings/billing")
                self.anthropic_client = None  # Disable to avoid repeated failures
            else:
                print(f"  [ERROR] Claude API call failed: {e}")
            return "Hi, I am interested in this property. Could you please send me more details? I would love to learn more about the price, availability, and any other relevant information."

    def extract_property_details(self, driver, url: str) -> Dict[str, str]:
        """Visits the property detail page and extracts the full description and other info."""
        print(f"\n  [DETAIL] Visiting {url}")
        driver.get(url)

        # --- Human behaviour: initial page-load settle ---
        human_delay(2500, 4500)

        # Simulate reading the page by scrolling down naturally
        print("  [HUMAN] Browsing page content...")
        human_scroll_and_read(driver)

        # Extra pause as if a human is looking at images or the map
        human_delay(800, 2000)

        details = {
            "description": "",
            "agent_phone": "",
            "agent_mail": "",
            "title": "",
            "address": "",
            "price": "",
            "propertyType": "",
            "size": "",
            "agent": "",
            "agency": "",
            "property_id": ""
        }

        # Extract Address
        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            details["address"] = h1.text.strip()
        except Exception:
            pass

        # Extract Title
        try:
            h2s = driver.find_elements(By.TAG_NAME, "h2")
            for h2 in h2s:
                txt = h2.text.strip()
                if txt and len(txt) > 10 and txt != "Property Description":
                    details["title"] = txt
                    break
        except Exception:
            pass

        # Extract Price
        try:
            # Primary: SVG icon with title 'Price' usually precedes the price span
            price_el = driver.find_element(By.XPATH, '//*[local-name()="svg"]/*[local-name()="title" and text()="Price"]/../..')
            details["price"] = price_el.text.strip()
        except Exception:
            try:
                # Fallback: legacy class match
                price_els = driver.find_elements(By.XPATH, '//*[contains(@class, "price") or contains(@class, "Price")]')
                for el in price_els:
                    txt = el.text.strip()
                    if txt and len(txt) < 50 and ('$' in txt or 'contact' in txt.lower() or 'application' in txt.lower() or 'lease' in txt.lower()):
                        details["price"] = txt
                        break
            except Exception:
                pass

        # Extract Size / Floor Area
        try:
            # Primary: data-testid attribute in the highlights table
            area_val = driver.find_element(By.CSS_SELECTOR, 'td[data-testid*="highlights-row-value Floor Area"], td[data-testid*="highlights-row-value Building Area"], td[data-testid*="highlights-row-value Land Area"]')
            details["size"] = area_val.get_attribute('textContent').strip()
        except Exception:
            try:
                # Fallback: label sibling
                area_label = driver.find_element(By.XPATH, '//div[contains(text(), "Floor Area") or contains(text(), "Building Area") or contains(text(), "Land Area")]/following-sibling::div')
                details["size"] = area_label.get_attribute('textContent').strip()
            except Exception:
                pass

        # Extract Property ID
        try:
            prop_id_val = driver.find_element(By.CSS_SELECTOR, 'td[data-testid*="highlights-row-value Property ID"]')
            details["property_id"] = prop_id_val.get_attribute('textContent').strip()
        except Exception:
            try:
                prop_id_label = driver.find_element(By.XPATH, '//div[contains(text(), "Property ID")]/following-sibling::div')
                details["property_id"] = prop_id_label.get_attribute('textContent').strip()
            except Exception:
                pass

        # Extract Property Type
        try:
            crumbs = driver.find_elements(By.CSS_SELECTOR, 'nav[aria-label="Breadcrumb"] a')
            if len(crumbs) >= 3:
                details["propertyType"] = crumbs[2].get_attribute('textContent').strip()
        except Exception:
            pass

        # Extract Agent
        try:
            agents = []
            agent_els = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/agent-profile/"]')
            for a in agent_els:
                txt = a.text.strip()
                if txt and txt not in agents:
                    agents.append(txt)
            details["agent"] = " | ".join(agents)
        except Exception:
            pass

        # Extract Agency
        try:
            agency_el = driver.find_element(By.CSS_SELECTOR, 'a[href*="/real-estate-agents/"]')
            details["agency"] = agency_el.text.strip()
        except Exception:
            pass

        # Extract Description
        try:
            # Common selectors for property descriptions
            desc_els = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="property-description"], div[class*="description"], div[class*="Description"]')
            for el in desc_els:
                if el.is_displayed() and len(el.text) > 50:
                    details["description"] = el.text
                    break
        except Exception:
            pass

        if not details["description"]:
            print("  [WARN] Could not find property description.")

        # Extract Agent Phone (if available)
        try:
            phone_els = driver.find_elements(By.XPATH, '//a[contains(@href, "tel:")]')
            for el in phone_els:
                if el.is_displayed():
                    details["agent_phone"] = el.text
                    break
        except Exception:
            pass
            
        # Extract Agent Email (if available)
        try:
            email_els = driver.find_elements(By.XPATH, '//a[contains(@href, "mailto:")]')
            for el in email_els:
                href = el.get_attribute("href")
                if href and "mailto:" in href:
                    details["agent_mail"] = href.replace("mailto:", "").split("?")[0]
                    break
        except Exception:
            pass

        return details

    def _reliable_clear(self, driver, element):
        """Clear a form field reliably using keyboard shortcuts.
        Works on React-controlled inputs where element.clear() often fails.
        """
        from selenium.webdriver.common.keys import Keys
        # Click to focus
        element.click()
        time.sleep(0.1)
        # Select all text (Ctrl+A) then delete — works universally
        element.send_keys(Keys.CONTROL + 'a')
        time.sleep(0.15)
        element.send_keys(Keys.DELETE)
        time.sleep(0.15)
        # Verify the field is empty; if not, try again with backspace flood
        current_val = driver.execute_script("return arguments[0].value;", element)
        if current_val:
            for _ in range(len(current_val) + 5):
                element.send_keys(Keys.BACKSPACE)
            time.sleep(0.1)

    def _verify_field_value(self, driver, element, expected: str) -> bool:
        """Read back the field value via JavaScript and check it matches."""
        actual = driver.execute_script("return arguments[0].value;", element)
        return actual.strip() == expected.strip()

    def submit_enquiry(self, driver, message: str) -> bool:
        """Finds the enquiry form on the detail page and submits it.
        All interactions use human-paced typing, mouse movement, and pauses.
        Includes verification + retry logic for the email field.
        """
        print("  [FORM] Locating enquiry form...")
        try:
            # 1. Check if we need to click an "Enquire Now" button first
            enquire_btns = driver.find_elements(By.XPATH, '//button[contains(translate(text(), "ENQUIR", "enquir"), "enquire")]')
            for btn in enquire_btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    human_delay(600, 1400)          # pause before clicking
                    human_mouse_move_to(driver, btn)
                    driver.execute_script("arguments[0].click();", btn)
                    print("  [FORM] Clicked 'Enquire' button to open modal.")
                    human_delay(1800, 3000)          # wait for modal animation
                    break

            # Wait for form inputs to be visible
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="name"], input[name*="Name"]'))
            )

            # --- A moment of hesitation before starting to fill the form ---
            human_delay(500, 1200)

            # --- Fill Name ---
            name_input = driver.find_element(By.CSS_SELECTOR, 'input[name="name"], input[name*="Name"]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", name_input)
            human_delay(200, 400)
            human_mouse_move_to(driver, name_input)
            name_input.click()
            human_delay(200, 450)
            self._reliable_clear(driver, name_input)
            print("  [FORM] Typing name...")
            human_type(name_input, ENQUIRY_NAME, wpm_range=(40, 65))
            human_delay(400, 900)   # brief pause after finishing the field

            # --- Fill Phone (moved before email so email verify is closer to submit) ---
            phone_input = driver.find_element(By.CSS_SELECTOR, 'input[name="phone"], input[name*="Phone"], input[type="tel"]')
            human_mouse_move_to(driver, phone_input)
            phone_input.click()
            human_delay(200, 450)
            self._reliable_clear(driver, phone_input)
            print("  [FORM] Typing phone...")
            human_type(phone_input, ENQUIRY_PHONE, wpm_range=(45, 70), allow_typos=False)
            human_delay(500, 1100)

            # --- Fill Email (typos DISABLED — emails have strict validation) ---
            email_input = driver.find_element(By.CSS_SELECTOR, 'input[name="email"], input[name*="Email"], input[type="email"]')
            email_typed_ok = False
            for attempt in range(1, 4):  # up to 3 attempts
                human_mouse_move_to(driver, email_input)
                email_input.click()
                human_delay(250, 550)
                self._reliable_clear(driver, email_input)
                print(f"  [FORM] Typing email (attempt {attempt})...")
                human_type(email_input, ENQUIRY_EMAIL, wpm_range=(30, 55), allow_typos=False)
                human_delay(400, 900)

                # --- Verify the email was typed correctly ---
                if self._verify_field_value(driver, email_input, ENQUIRY_EMAIL):
                    print("  [FORM] Email verified OK.")
                    email_typed_ok = True
                    break
                else:
                    actual = driver.execute_script("return arguments[0].value;", email_input)
                    print(f"  [WARN] Email mismatch! Expected '{ENQUIRY_EMAIL}' but got '{actual}'. Retrying...")
                    human_delay(500, 1000)

            if not email_typed_ok:
                # Last resort: force-set via JavaScript and trigger change event
                print("  [WARN] Email retry failed 3 times. Force-setting via JS.")
                driver.execute_script(
                    "var el = arguments[0]; "
                    "var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; "
                    "nativeInputValueSetter.call(el, arguments[1]); "
                    "el.dispatchEvent(new Event('input', { bubbles: true })); "
                    "el.dispatchEvent(new Event('change', { bubbles: true }));",
                    email_input, ENQUIRY_EMAIL
                )
                human_delay(300, 600)

            # --- Fill Message (longest field — type slowest) ---
            msg_input = driver.find_element(By.CSS_SELECTOR, 'textarea[name="message"], textarea[name*="Message"]')
            human_mouse_move_to(driver, msg_input)
            msg_input.click()
            human_delay(400, 800)   # pause as if thinking about what to write
            self._reliable_clear(driver, msg_input)
            print("  [FORM] Typing message (this will take a moment)...")
            human_type(msg_input, message, wpm_range=(28, 50))
            human_delay(800, 1800)  # review pause after writing message

            # --- Final email sanity check before submit ---
            final_email = driver.execute_script("return arguments[0].value;", email_input)
            if final_email.strip() != ENQUIRY_EMAIL.strip():
                print(f"  [WARN] Final email check failed: '{final_email}'. Force-correcting...")
                driver.execute_script(
                    "var el = arguments[0]; "
                    "var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; "
                    "nativeInputValueSetter.call(el, arguments[1]); "
                    "el.dispatchEvent(new Event('input', { bubbles: true })); "
                    "el.dispatchEvent(new Event('change', { bubbles: true }));",
                    email_input, ENQUIRY_EMAIL
                )
                human_delay(300, 500)

            # --- Locate submit button and click ---
            submit_btn = driver.find_element(By.XPATH, '//button[@type="submit" or contains(translate(text(), "SEND", "send"), "send")]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            human_delay(300, 600)
            human_mouse_move_to(driver, submit_btn)
            human_delay(300, 700)   # hover briefly over submit, then click
            driver.execute_script("arguments[0].click();", submit_btn)
            print("  [FORM] Form filled and submitted successfully!")
            return True

        except Exception as e:
            print(f"  [ERROR] Failed to submit enquiry form: {e}")
            return False

    def is_already_enquired(self, url: str) -> bool:
        """Checks Google Sheets if this URL has already been processed."""
        if not self.sheet:
            return False
        
        try:
            # URL is in column 'I' (9th column) based on the new sheet format
            urls_in_sheet = self.sheet.col_values(9)
            return url in urls_in_sheet
        except Exception as e:
            print(f"  [WARN] Failed to read from Google Sheets: {e}")
            return False

    def log_to_sheet(self, listing: dict, detail_info: dict, message: str, status: str):
        """Appends the result to Google Sheets."""
        if not self.sheet:
            return
        
        try:
            tags_val = " | ".join(listing.get("tags", [])) if isinstance(listing.get("tags"), list) else listing.get("tags", "")
            
            row = [
                listing.get("title", ""),
                listing.get("address", ""),
                listing.get("price", ""),
                listing.get("propertyType", ""),
                listing.get("size", ""),
                listing.get("agent", ""),
                "", # agent_mail (not extracted currently)
                listing.get("agency", ""),
                listing.get("link", ""),
                listing.get("image", ""),
                tags_val,
                listing.get("page_num", ""),
                listing.get("location_query", ""),
                message,
                time.strftime("%Y-%m-%d %H:%M:%S"),
                detail_info.get("property_id", "")
            ]
            # Find the next empty row dynamically to avoid Google Sheets API append bugs with empty columns
            next_row = len(self.sheet.get_all_values()) + 1
            self.sheet.update(range_name=f"A{next_row}", values=[row])
            print(f"  [OK] Saved to Google Sheets at row {next_row}.")
        except Exception as e:
            print(f"  [ERROR] Failed to save to Google Sheets: {e}")

    def process_listings(self, driver, listings: list[dict]):
        """Main orchestrator for processing a list of scraped properties.

        Human-behaviour enhancements:
          - Random inter-listing delay (3-8 s) to simulate reading time between visits
          - Occasional longer 'coffee break' pause every 8-15 listings (15-35 s)
          - Shuffled listing order so visits don't follow a deterministic pattern
        """
        print(f"\n============================================================")
        print(f"  [ENQUIRY] Starting Phase 2 for {len(listings)} listings...")
        print(f"============================================================")

        # Randomise visit order slightly (swap up to 30% of adjacent pairs)
        shuffled = listings[:]
        for i in range(len(shuffled) - 1):
            if random.random() < 0.30:
                shuffled[i], shuffled[i + 1] = shuffled[i + 1], shuffled[i]

        # Each 'session block' is 8-15 listings before a longer rest
        next_break_at = random.randint(8, 15)

        for idx, listing in enumerate(shuffled):
            url = listing.get("link")
            if not url:
                continue

            print(f"\n[{idx+1}/{len(shuffled)}] Processing: {listing.get('title')}")

            if self.is_already_enquired(url):
                print("  [SKIP] Already enquired (found in Google Sheets).")
                continue

            # 1. Extract Details
            detail_info = self.extract_property_details(driver, url)
            
            # MERGE detail_info into listing to fill blanks from the listing page
            for key in ["title", "address", "price", "propertyType", "size", "agent", "agency"]:
                if detail_info.get(key) and not listing.get(key):
                    listing[key] = detail_info[key]
            
            if not detail_info["description"]:
                print("  [SKIP] No description found, skipping enquiry.")
                human_delay(1500, 3000)
                continue

            # 2. Get Claude Message (Pass Property ID to Claude)
            full_description = detail_info["description"]
            if detail_info.get("property_id"):
                full_description = f"Property ID: {detail_info['property_id']}\n\n" + full_description
                
            message = self.get_claude_enquiry_message(full_description)

            # 3. Submit Form
            success = self.submit_enquiry(driver, message)

            status = "Success" if success else "Failed to Submit"

            # 4. Log to Sheets
            self.log_to_sheet(listing, detail_info, message, status)

            # --- Inter-listing delay (human reads confirmation, checks email, etc.) ---
            if (idx + 1) >= next_break_at:
                # Simulate a longer break every N listings
                rest = random.uniform(15, 35)
                print(f"  [HUMAN] Taking a short break ({rest:.0f}s) before continuing...")
                time.sleep(rest)
                next_break_at += random.randint(8, 15)
            else:
                human_delay(3000, 8000)
