import os
import json
import time
import random
import re
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
    ENQUIRY_NAME, ENQUIRY_EMAIL, ENQUIRY_PHONE, ENQUIRY_MESSAGE_TEMPLATE,
    CLAUDE_PROMPT_CRITERIA,
)

def human_delay(min_ms: int = 800, max_ms: int = 2500):
    """Random pause in a human-plausible range."""
    time.sleep(random.uniform(min_ms / 1000.0, max_ms / 1000.0))


def human_type(element, text: str, wpm_range=(35, 75), allow_typos: bool = False):
    """Type text character-by-character with a realistic WPM speed.
    Artificial typos have been disabled to ensure stability with React forms.
    """
    # Convert WPM to per-character delay (avg 5 chars per word)
    wpm = random.uniform(*wpm_range)
    base_delay = 60.0 / (wpm * 5)  # seconds per character

    for char in text:
        element.send_keys(char)
        # Variable keystroke delay with occasional micro-pauses (thinking)
        delay = base_delay * random.uniform(0.5, 1.8)
        if random.random() < 0.05:          # ~5% chance of a longer hesitation
            delay += random.uniform(0.1, 0.4)
        time.sleep(delay)


def human_type_cdp(driver, element, text: str, wpm_range=(35, 75)):
    """Type text using Chrome DevTools Protocol (CDP) — works even when Chrome
    is in the background / unfocused.  send_keys relies on OS-level keyboard
    focus, so characters get silently dropped when the window isn't active.
    CDP's Input.dispatchKeyEvent bypasses the OS input queue entirely.
    """
    # Focus the element first via JS (CDP needs a focused target)
    driver.execute_script(
        "arguments[0].focus(); arguments[0].click();", element
    )
    time.sleep(0.15)

    wpm = random.uniform(*wpm_range)
    base_delay = 60.0 / (wpm * 5)

    for char in text:
        # Use CDP insertText command — most reliable for React controlled inputs
        driver.execute_cdp_cmd("Input.insertText", {"text": char})
        delay = base_delay * random.uniform(0.5, 1.8)
        if random.random() < 0.05:
            delay += random.uniform(0.1, 0.4)
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

    def get_enquiry_message(self, agent_name_raw: str) -> str:
        """Build the enquiry message using the fixed template from config.
        Substitutes the agent's first name, or 'there' if unknown."""
        agent_first = "there"
        if agent_name_raw:
            # Take the first agent name before any delimiter (| , /)
            first_agent = re.split(r'[|,/]', agent_name_raw)[0].strip()
            if first_agent:
                # Take first name only
                agent_first = first_agent.split()[0].strip()

        message = ENQUIRY_MESSAGE_TEMPLATE.format(agent_name=agent_first)
        print(f"  [MSG] Using template message (agent: {agent_first})")
        return message

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

    def _reliable_clear_cdp(self, driver, element):
        """Clear a form field using CDP — works even when Chrome is backgrounded.
        Falls back to JS-based clearing if CDP clear fails.
        """
        # Focus the element
        driver.execute_script("arguments[0].focus(); arguments[0].click();", element)
        time.sleep(0.15)

        # Select all via CDP keyboard shortcut
        try:
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "a", "code": "KeyA",
                "windowsVirtualKeyCode": 65, "modifiers": 2  # 2 = Ctrl
            })
            time.sleep(0.05)
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "a", "code": "KeyA",
                "windowsVirtualKeyCode": 65, "modifiers": 2
            })
            time.sleep(0.1)
            # Delete the selected text
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Backspace", "code": "Backspace",
                "windowsVirtualKeyCode": 8
            })
            time.sleep(0.05)
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Backspace", "code": "Backspace",
                "windowsVirtualKeyCode": 8
            })
            time.sleep(0.15)
        except Exception:
            # Fallback: JS-based clear
            pass

        # Verify it's empty; if not, brute-force clear via JS
        current_val = driver.execute_script("return arguments[0].value;", element)
        if current_val:
            self._force_react_value(driver, element, "",
                                    is_textarea=(element.tag_name.lower() == "textarea"))
            time.sleep(0.15)

    def _verify_field_value(self, driver, element, expected: str) -> bool:
        """Read back the field value via JavaScript and check it matches."""
        actual = driver.execute_script("return arguments[0].value;", element)
        return actual.strip() == expected.strip()

    def _force_react_value(self, driver, element, value: str, is_textarea: bool = False):
        """Force sets the value of a React-controlled input/textarea using the
        native prototype setter and dispatches the full event sequence that React's
        synthetic event system listens for: focus → focusin → input → change → blur.
        """
        prototype = "HTMLTextAreaElement" if is_textarea else "HTMLInputElement"
        driver.execute_script("""
            var el = arguments[0];
            var value = arguments[1];
            var proto = arguments[2];

            // 1. Focus the element
            el.focus();
            el.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));

            // 2. Use the native setter to bypass React's value lock
            var setter = Object.getOwnPropertyDescriptor(
                window[proto].prototype, 'value'
            );
            if (setter && setter.set) {
                setter.set.call(el, value);
            } else {
                el.value = value;
            }

            // 3. Fire InputEvent (React 16+ listens for this, not generic Event)
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true,
                inputType: 'insertText', data: value
            }));

            // 4. Fire change event
            el.dispatchEvent(new Event('change', { bubbles: true }));

            // 5. Blur to trigger any onBlur validation the form may have
            el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
            el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
        """, element, value, prototype)

    def _fill_field_reliably(self, driver, element, value: str,
                              field_name: str, is_textarea: bool = False,
                              wpm_range=(35, 65)):
        """Fill a single form field with guaranteed correctness.

        Strategy:
          1. Clear field using CDP
          2. Type via CDP (works in background)
          3. Verify value matches
          4. If mismatch → force-set via React JS injection + verify again
          5. Repeat up to 3 full cycles
        """
        for cycle in range(1, 4):
            # Clear
            self._reliable_clear_cdp(driver, element)
            human_delay(150, 300)

            # Type via CDP
            print(f"  [FORM] Typing {field_name} (cycle {cycle})...")
            human_type_cdp(driver, element, value, wpm_range=wpm_range)
            human_delay(300, 600)

            # Verify
            if self._verify_field_value(driver, element, value):
                print(f"  [FORM] {field_name} verified OK.")
                return True

            actual = driver.execute_script("return arguments[0].value;", element)
            print(f"  [WARN] {field_name} mismatch after CDP typing! "
                  f"Expected '{value[:40]}...' but got '{actual[:40]}...'. "
                  f"Force-correcting...")

            # Force-set via React-aware JS
            self._force_react_value(driver, element, value, is_textarea=is_textarea)
            human_delay(300, 500)

            if self._verify_field_value(driver, element, value):
                print(f"  [FORM] {field_name} verified OK after JS force-set.")
                return True

            print(f"  [WARN] {field_name} still wrong after cycle {cycle}. "
                  f"{'Retrying...' if cycle < 3 else 'Giving up on re-type, will catch in final gate.'}")
            human_delay(300, 500)

        return False

    def _verify_all_fields_before_submit(self, driver, fields: dict) -> bool:
        """Final validation gate: checks ALL form fields match their expected
        values.  If any field is wrong, force-corrects it and re-checks.
        Returns True only when every field is confirmed correct.

        `fields` is a dict of { "Name": (element, expected_value, is_textarea), ... }
        """
        MAX_GATE_ATTEMPTS = 3
        for gate_attempt in range(1, MAX_GATE_ATTEMPTS + 1):
            all_ok = True
            for field_name, (element, expected, is_textarea) in fields.items():
                actual = driver.execute_script("return arguments[0].value;", element)
                if actual.strip() != expected.strip():
                    all_ok = False
                    print(f"  [GATE] {field_name} FAILED (attempt {gate_attempt}): "
                          f"got '{actual[:50]}...' — force-correcting...")
                    self._force_react_value(driver, element, expected, is_textarea=is_textarea)
                    human_delay(200, 400)

            if all_ok:
                print("  [GATE] ✓ All fields verified — safe to submit.")
                return True

            human_delay(300, 600)

        # Last resort: one more read to see where we stand
        still_bad = []
        for field_name, (element, expected, is_textarea) in fields.items():
            actual = driver.execute_script("return arguments[0].value;", element)
            if actual.strip() != expected.strip():
                still_bad.append(field_name)
        if still_bad:
            print(f"  [GATE] ✗ Fields still incorrect after {MAX_GATE_ATTEMPTS} attempts: {still_bad}")
            return False
        return True

    def submit_enquiry(self, driver, message: str) -> bool:
        """Finds the enquiry form on the detail page and submits it.

        Uses CDP-based typing (background-safe) with multi-layer verification:
          1. Type each field via CDP (works even when Chrome is unfocused)
          2. Verify each field immediately after typing
          3. Force-correct any mismatches via React-aware JS injection
          4. Run a final validation gate on ALL fields before clicking Submit
          5. Only click Submit if every field is confirmed correct
        """
        print("  [FORM] Locating enquiry form...")
        try:
            # 1. Check if we need to click an "Enquire Now" button first
            enquire_btns = driver.find_elements(By.XPATH, '//button[contains(translate(text(), "ENQUIR", "enquir"), "enquire")]')
            for btn in enquire_btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    human_delay(600, 1400)
                    human_mouse_move_to(driver, btn)
                    driver.execute_script("arguments[0].click();", btn)
                    print("  [FORM] Clicked 'Enquire' button to open modal.")
                    human_delay(1800, 3000)
                    break

            # Wait for form inputs to be visible
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="name"], input[name*="Name"]'))
            )

            # --- A moment of hesitation before starting to fill the form ---
            human_delay(500, 1200)

            # --- Locate all form elements up front ---
            name_input  = driver.find_element(By.CSS_SELECTOR, 'input[name="name"], input[name*="Name"]')
            phone_input = driver.find_element(By.CSS_SELECTOR, 'input[name="phone"], input[name*="Phone"], input[type="tel"]')
            email_input = driver.find_element(By.CSS_SELECTOR, 'input[name="email"], input[name*="Email"], input[type="email"]')
            msg_input   = driver.find_element(By.CSS_SELECTOR, 'textarea[name="message"], textarea[name*="Message"]')

            # --- Fill Name ---
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", name_input)
            human_delay(200, 400)
            human_mouse_move_to(driver, name_input)
            self._fill_field_reliably(driver, name_input, ENQUIRY_NAME,
                                       "Name", is_textarea=False, wpm_range=(40, 65))
            human_delay(400, 900)

            # --- Fill Phone ---
            human_mouse_move_to(driver, phone_input)
            self._fill_field_reliably(driver, phone_input, ENQUIRY_PHONE,
                                       "Phone", is_textarea=False, wpm_range=(45, 70))
            human_delay(500, 1100)

            # --- Fill Email ---
            human_mouse_move_to(driver, email_input)
            self._fill_field_reliably(driver, email_input, ENQUIRY_EMAIL,
                                       "Email", is_textarea=False, wpm_range=(30, 55))
            human_delay(400, 900)

            # --- Fill Message (longest field) ---
            human_mouse_move_to(driver, msg_input)
            human_delay(400, 800)
            self._fill_field_reliably(driver, msg_input, message,
                                       "Message", is_textarea=True, wpm_range=(28, 50))
            human_delay(800, 1800)

            # ============================================================
            #  FINAL VALIDATION GATE — do NOT submit unless ALL fields OK
            # ============================================================
            fields_to_check = {
                "Name":    (name_input,  ENQUIRY_NAME,  False),
                "Phone":   (phone_input, ENQUIRY_PHONE, False),
                "Email":   (email_input, ENQUIRY_EMAIL, False),
                "Message": (msg_input,   message,       True),
            }
            if not self._verify_all_fields_before_submit(driver, fields_to_check):
                print("  [ERROR] Form fields could not be verified. SKIPPING submit to avoid empty enquiry.")
                return False

            # --- Locate submit button and click ---
            submit_btn = driver.find_element(By.XPATH, '//button[@type="submit" or contains(translate(text(), "SEND", "send"), "send")]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            human_delay(300, 600)
            human_mouse_move_to(driver, submit_btn)
            human_delay(300, 700)
            driver.execute_script("arguments[0].click();", submit_btn)
            print("  [FORM] ✓ Form filled and submitted successfully!")
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
        """Appends the result to Google Sheets by mapping data to column headers."""
        if not self.sheet:
            return
        
        try:
            # Get headers to map data correctly
            headers = self.sheet.row_values(1)
            
            # If headers are empty, we can't reliably map, so we'll just append
            if not headers:
                print("  [WARN] Sheet has no headers in row 1. Cannot map columns.")
                return

            tags_val = " | ".join(listing.get("tags", [])) if isinstance(listing.get("tags"), list) else listing.get("tags", "")
            
            # Create an empty row of the same length as headers
            row_data = [""] * len(headers)
            
            # Helper to safely set a value if the column exists
            def set_col(col_names, val):
                for name in col_names:
                    # Match case-insensitive
                    idx = next((i for i, h in enumerate(headers) if h.lower().strip() == name.lower()), -1)
                    if idx != -1:
                        row_data[idx] = val
                        return

            set_col(["title", "Title"], listing.get("title", ""))
            set_col(["address", "Address"], listing.get("address", ""))
            set_col(["price", "Price", "Asking prize"], listing.get("price", ""))
            set_col(["propertyType", "Property Type"], listing.get("propertyType", ""))
            set_col(["size", "Size (sqm)"], listing.get("size", ""))
            set_col(["agent", "Agent"], listing.get("agent", ""))
            set_col(["agency", "Agency"], listing.get("agency", ""))
            set_col(["link", "Listing Link"], listing.get("link", ""))
            set_col(["image", "Image"], listing.get("image", ""))
            set_col(["tags", "Tags"], tags_val)
            set_col(["page_num", "Page Num"], listing.get("page_num", ""))
            set_col(["location_query", "Location Query"], listing.get("location_query", ""))
            set_col(["message", "agent_message", "Message"], message)
            set_col(["scraped_at", "Scraped At"], time.strftime("%Y-%m-%d %H:%M:%S"))
            set_col(["property_id", "PID"], detail_info.get("property_id", ""))
            
            # The new Purchase Price column requested by user
            set_col(["Purchase Price", "Purchase price"], listing.get("price", ""))

            # Append the row by explicitly finding the next empty row
            next_row = len(self.sheet.get_all_values()) + 1
            self.sheet.update(range_name=f"A{next_row}", values=[row_data], value_input_option="USER_ENTERED")
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

            # 2. Build enquiry message from template (no Claude call needed)
            agent_name_raw = listing.get("agent", "") or detail_info.get("agent", "")
            message = self.get_enquiry_message(agent_name_raw)

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
