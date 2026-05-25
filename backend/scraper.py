
import os
import re
import json
import time
import random
import csv
from datetime import datetime
from urllib.parse import urlencode, urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    from enquiry_agent import EnquiryAgent
except ImportError:
    EnquiryAgent = None

BASE_URL = "https://www.commercialrealestate.com.au"

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[^\x00-\x7F\xA0]+', ' ', text)
    text = text.replace('\xa0', ' ')
    return " ".join(text.split())

def slugify_location(location: str) -> str:
    s = location.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s).strip('-')
    return s

def build_search_url(location_slug: str, keyword: str, min_size: int, max_size: int, listing_type: str, page_num: int) -> str:
    path = f"/{listing_type}/{location_slug}/"
    params = {}
    if keyword:
        params["kw"] = keyword
    if min_size > 0 or max_size > 0:
        min_str = str(min_size) if min_size > 0 else "0"
        max_str = str(max_size) if max_size > 0 else ""
        params["bs"] = f"{min_str},{max_str}"
    if page_num > 1:
        params["page"] = page_num
    
    if params:
        return f"{BASE_URL}{path}?{urlencode(params)}"
    return f"{BASE_URL}{path}"

def human_delay(min_ms: int = 800, max_ms: int = 2500):
    time.sleep(random.uniform(min_ms / 1000.0, max_ms / 1000.0))

def scroll_page(driver, steps=5):
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {random.randint(400, 800)});")
        human_delay(300, 800)

def extract_listings_from_page(driver) -> list[dict]:
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/property/"]'))
        )
    except TimeoutException:
        print("  [WARN]  No property links found - may be blocked or results empty.")
        return []

    human_delay(1000, 2000)

    raw = driver.execute_script("""
        const results = [];
        const seen = new Set();
        const propertyLinks = document.querySelectorAll('a[href*="/property/"]');

        propertyLinks.forEach(linkEl => {
            const href = linkEl.href;
            if (seen.has(href)) return;
            seen.add(href);

            let card = linkEl;
            for (let i = 0; i < 8; i++) {
                const parent = card.parentElement;
                if (!parent) break;
                const tag = parent.tagName.toLowerCase();
                if (tag === 'li' || tag === 'article') { card = parent; break; }
                if (tag === 'div' && parent.children.length >= 2) { card = parent; break; }
                card = parent;
            }

            const getText = (...selectors) => {
                for (const s of selectors) {
                    const el = card.querySelector(s);
                    if (el) {
                        const txt = el.innerText ? el.innerText.trim() : el.textContent.trim();
                        if (txt) return txt;
                    }
                }
                return '';
            };

            let title = getText('h2', 'h3', 'h4', 'h1') ||
                          (linkEl.getAttribute('aria-label') || '').split(' at ')[0].trim() ||
                          linkEl.innerText.trim();

            let address = '';
            const ariaLabel = linkEl.getAttribute('aria-label') || '';
            if (ariaLabel.includes(' at ')) {
                address = ariaLabel.split(' at ')[1] || '';
            }
            if (!address) {
                const addrEl = card.querySelector('[class*="address"], [class*="Address"], [class*="location"]');
                if (addrEl) address = addrEl.innerText.trim();
            }

            // Fallback: parse address/title from the URL slug if DOM extraction failed
            if (!address || !title) {
                try {
                    const parts = href.split('/property/');
                    if (parts.length > 1) {
                        let slug = parts[1].split('-')[0] === '' ? parts[1].slice(1) : parts[1]; // Remove leading hyphen if any
                        slug = slug.split('-').slice(0, -1).join(' '); // Remove property ID at the end
                        // capitalize words
                        const prettySlug = slug.replace(/\\b\\w/g, l => l.toUpperCase());
                        if (!address) address = prettySlug;
                        if (!title) title = prettySlug;
                    }
                } catch(e) {}
            }

            const price = getText('[class*="price"], [class*="Price"]');
            const propertyType = getText('[class*="propertyType"], [class*="category"], [class*="type"]');

            let size = '';
            card.querySelectorAll('span, p, div').forEach(el => {
                const txt = el.innerText ? el.innerText.trim() : '';
                if (/(?:\\d+)\\s*(?:m2|m²|sqm)/i.test(txt) && txt.length < 50 && !size) {
                    size = txt;
                }
            });

            const agent = getText('[class*="agent"], [class*="Agent"]');
            const agency = getText('[class*="agency"], [class*="Agency"], [class*="brand"], [class*="Brand"]');

            const imgEl = card.querySelector('img[src], img[data-src]');
            const image = imgEl ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '') : '';

            const tags = [];
            card.querySelectorAll('[class*="badge"], [class*="tag"], [class*="label"], [class*="Badge"]').forEach(t => {
                const txt = t.innerText ? t.innerText.trim() : '';
                if (txt && txt.length < 40) tags.push(txt);
            });

            results.push({
                title: title.substring(0, 200),
                address: address.substring(0, 200),
                price: price.substring(0, 100),
                propertyType: propertyType.substring(0, 100),
                size: size.substring(0, 50),
                agent: agent.substring(0, 100),
                agency: agency.substring(0, 100),
                link: href,
                image: image.substring(0, 500),
                tags: [...new Set(tags)],
            });
        });
        return results;
    """)

    for item in raw:
        for k, v in item.items():
            if isinstance(v, str):
                item[k] = clean_text(v)
            elif isinstance(v, list):
                item[k] = [clean_text(i) for i in v]
    return raw

def navigate_via_search_ui(driver, location: str, keyword: str, min_size: int, max_size: int, listing_type: str) -> bool:
    print(f"  [UI]  Using homepage search bar for: location='{location}', keyword='{keyword}'")
    try:
        location_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[placeholder*="state, suburb or postcode" i], input[placeholder*="location" i]'))
        )
        human_delay(500, 1000)
        location_input.click()
        
        from selenium.webdriver.common.keys import Keys
        # Type character by character
        for char in location:
            location_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        
        print("  [UI]  Waiting for autocomplete dropdown...")
        human_delay(2000, 3500)
        
        try:
            # Try to explicitly click the first suggestion in the dropdown
            suggestions = driver.find_elements(By.CSS_SELECTOR, 'li[role="option"], div[role="option"], ul[class*="suggest"] li, [class*="Autocomplete"] li')
            clicked = False
            for suggestion in suggestions:
                if suggestion.is_displayed():
                    suggestion.click()
                    clicked = True
                    print("  [UI]  Successfully clicked the first autocomplete suggestion.")
                    break
            
            # Fallback if dropdown elements aren't found by CSS
            if not clicked:
                print("  [UI]  No dropdown elements found, falling back to ENTER.")
                location_input.send_keys(Keys.ENTER)
        except Exception as e:
            print(f"  [WARN]  Failed autocomplete selection: {e}")
            location_input.send_keys(Keys.ENTER)

        human_delay(800, 1500)

        # Click Search button
        print("  [UI]  Clicking Search button...")
        search_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Search')]")
        search_clicked = False
        for btn in search_btns:
            if btn.is_displayed():
                human_delay(300, 700)
                driver.execute_script("arguments[0].click();", btn)
                search_clicked = True
                print(f"  [UI]  Clicked a search button")
                break
                
        human_delay(1000, 2000)
        return True
    except Exception as e:
        print(f"  [WARN]  UI navigation error: {e}")
        return False

def apply_filters_on_results_page(driver, keyword: str):
    print(f"  [INFO]  Applying full filters via UI on the results page...")
    try:
        if keyword:
            kw_els = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder*="keyword" i]')
            kw_el = next((el for el in kw_els if el.is_displayed()), None)
            if kw_el:
                kw_el.click()
                human_delay(200, 400)
                kw_el.clear()
                for char in keyword:
                    kw_el.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.12))
                print(f"  [UI]  Typed keyword: '{keyword}' on results page")
                human_delay(500, 1000)
        
        # Click search button
        search_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Search')]")
        for btn in search_btns:
            if btn.is_displayed():
                human_delay(300, 700)
                driver.execute_script("arguments[0].click();", btn)
                print(f"  [UI]  Clicked Search button on results page")
                break
                
        human_delay(3000, 5000)
    except Exception as e:
        print(f"  [WARN]  Failed to apply filters via UI: {e}")

def run_scraper(location: str, keyword: str, min_size: int, max_size: int, listing_type: str, max_pages: int, fetch_details: bool, output_dir: str, manual_warmup: bool = False) -> list[dict]:
    location_slug = slugify_location(location)
    all_listings = []

    profile_dir = os.path.join(os.path.expanduser("~"), ".cre_scraper_profile_uc")
    os.makedirs(output_dir, exist_ok=True)

    # --- Clean up stale Chrome lock files to prevent SessionNotCreatedException ---
    for lock_file in ["lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(profile_dir, lock_file)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                print(f"  [INFO]  Removed stale Chrome lock: {lock_file}")
            except Exception:
                pass

    options = uc.ChromeOptions()
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")

    print(f"  [INFO]  Starting undetected-chromedriver...")
    driver = None
    for attempt in range(1, 4):
        try:
            driver = uc.Chrome(
                options=options,
                user_data_dir=profile_dir,
                use_subprocess=True,
                version_main=148
            )
            break
        except Exception as e:
            print(f"  [WARN]  Chrome start attempt {attempt} failed: {e}")
            if attempt < 3:
                print(f"  [INFO]  Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise RuntimeError("Could not start Chrome after 3 attempts. Please close any open Chrome windows and retry.") from e

    try:
        driver.set_page_load_timeout(60)
        
        print("  [INFO]  Opening homepage to warm up session & pass Cloudflare...")
        driver.get(BASE_URL + "/")
        
        human_delay(3000, 5000)
        page_title = driver.title
        
        if "access denied" in page_title.lower() or "just a moment" in page_title.lower():
            print("  [CLOUDFLARE]  Challenge detected on homepage. Waiting...")
            human_delay(5000, 10000)

        # Step 1: UI Search on homepage to bypass Cloudflare
        print(f"\n  [PAGE 1]  Bypassing Cloudflare via basic UI search...")
        navigate_via_search_ui(driver, location, "", min_size, max_size, listing_type)
        
        current_url = driver.current_url
        
        # Extract the real location slug from the URL the website redirected us to
        parsed = urlparse(current_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) >= 2 and path_parts[0] in ["for-lease", "for-sale", "sold", "leased"]:
            real_location_slug = path_parts[1]
            print(f"  [INFO]  Extracted actual location slug from website: {real_location_slug}")
            location_slug = real_location_slug
        
        # Now that we have warmed up the session and CF clearance, we can just navigate directly
        # undetected_chromedriver bypasses the block that Playwright was hitting here.
        first_page_url = build_search_url(location_slug, keyword, min_size, max_size, listing_type, 1)
        print(f"  [INFO]  Navigating directly to true query URL: {first_page_url}")
        driver.get(first_page_url)
        human_delay(2000, 4000)

        # Check if blocked
        page_title = driver.title
        if "access denied" in page_title.lower() or "just a moment" in page_title.lower():
            print(f"  [ERROR]  Still blocked! Title: '{page_title}'")
            print("  [TIP]   Solve the CAPTCHA manually in the browser window, then restart the script.")
            return all_listings

        print(f"  [OK]  Results page loaded: '{page_title}'")
        print(f"  [URL]  {driver.current_url}")

        for page_num in range(1, max_pages + 1):
            if page_num > 1:
                url = build_search_url(location_slug, keyword, min_size, max_size, listing_type, page_num)
                print(f"\n  [PAGE {page_num}/{max_pages}]  {url}")
                try:
                    driver.get(url)
                    human_delay(2000, 4000)
                except Exception as e:
                    print(f"  [ERROR]  Page {page_num} failed: {e}")
                    break

            scroll_page(driver, steps=random.randint(4, 7))
            
            listings = extract_listings_from_page(driver)
            print(f"  [OK]  Extracted {len(listings)} listings from page {page_num}")

            if not listings:
                print("  [WARN]  No listings extracted - stopping pagination.")
                break

            for listing in listings:
                listing["page_num"] = page_num
                listing["location_query"] = location
                listing["scraped_at"] = datetime.now().isoformat()
            
            all_listings.extend(listings)
            human_delay(2000, 5000)

        # Save output
        if all_listings:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"cre_{location_slug}_{keyword}_{timestamp}"
            
            json_path = os.path.join(output_dir, f"{base_filename}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(all_listings, f, indent=2, ensure_ascii=False)
            
            csv_path = os.path.join(output_dir, f"{base_filename}.csv")
            keys = ["title", "address", "price", "propertyType", "size", "agent", "agency", "link", "image", "tags", "page_num", "location_query", "scraped_at"]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                for row in all_listings:
                    row_copy = row.copy()
                    row_copy["tags"] = " | ".join(row.get("tags", []))
                    writer.writerow(row_copy)
            
            print(f"\n============================================================")
            print(f"  [SAVE]  Saving {len(all_listings)} listings...")
            print(f"  [FILE]  JSON: {json_path}")
            print(f"  [FILE]  CSV : {csv_path}")
            print(f"\n  [DONE]  {len(all_listings)} properties scraped successfully!")
            print(f"============================================================")

            if fetch_details:
                if EnquiryAgent is None:
                    print("  [WARN] EnquiryAgent module not found. Skipping Phase 2.")
                else:
                    agent = EnquiryAgent()
                    # Processing all listings end-to-end
                    agent.process_listings(driver, all_listings)
                    
                    # Re-save the enriched data to CSV/JSON after details extraction
                    print(f"\n  [SAVE]  Re-saving {len(all_listings)} enriched listings...")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(all_listings, f, indent=2, ensure_ascii=False)
                    with open(csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                        writer.writeheader()
                        for row in all_listings:
                            row_copy = row.copy()
                            row_copy["tags"] = " | ".join(row.get("tags", []))
                            writer.writerow(row_copy)
                    print("  [DONE]  Enriched data saved successfully!")

    except Exception as e:
        print(f"  [ERROR]  Critical scraper failure: {e}")
    finally:
        print("  [INFO]  Closing browser...")
        driver.quit()

    return all_listings
