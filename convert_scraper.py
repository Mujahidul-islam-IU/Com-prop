import os

new_scraper = r'''
import os
import re
import json
import time
import random
import csv
from datetime import datetime
from urllib.parse import urlencode

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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

def build_search_url(location_slug: str, keyword: str, min_size: int, listing_type: str, page_num: int) -> str:
    path = f"/{listing_type}/{location_slug}/"
    params = {}
    if keyword:
        params["kw"] = keyword
    if min_size > 0:
        params["bs"] = f"{min_size},"
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

            const title = getText('h2', 'h3', 'h4', 'h1') ||
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

def navigate_via_search_ui(driver, location: str, keyword: str, min_size: int, listing_type: str) -> bool:
    print(f"  [UI]  Using homepage search bar for: location='{location}', keyword='{keyword}'")
    try:
        location_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[placeholder*="state, suburb or postcode" i], input[placeholder*="location" i]'))
        )
        human_delay(500, 1000)
        location_input.click()
        
        # Type character by character
        for char in location:
            location_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        
        print("  [UI]  Waiting for autocomplete dropdown...")
        human_delay(2000, 3500)
        
        try:
            # Look for <li> containing the text
            suggestion = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//li[contains(text(), '{location}')]"))
            )
            human_delay(300, 600)
            suggestion.click()
            print(f"  [UI]  Successfully clicked autocomplete suggestion for '{location}'")
        except TimeoutException:
            print(f"  [WARN]  Failed to find suggestion for '{location}'")

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

def run_scraper(location: str, keyword: str, min_size: int, listing_type: str, max_pages: int, fetch_details: bool, output_dir: str, manual_warmup: bool = False) -> list[dict]:
    location_slug = slugify_location(location)
    all_listings = []

    profile_dir = os.path.join(os.path.expanduser("~"), ".cre_scraper_profile_uc")
    os.makedirs(output_dir, exist_ok=True)

    options = uc.ChromeOptions()
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")

    print(f"  [INFO]  Starting undetected-chromedriver...")
    driver = uc.Chrome(
        options=options,
        user_data_dir=profile_dir,
        use_subprocess=True
    )

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
        navigate_via_search_ui(driver, location, "", min_size, listing_type)
        
        current_url = driver.current_url
        is_on_results_page = False
        if "/for-sale/" in current_url or "/for-lease/" in current_url or "/sold/" in current_url or "/leased/" in current_url:
            is_on_results_page = True
            print(f"  [UI]  Successfully gained CF clearance for: {current_url[:60]}...")
        else:
            print(f"  [UI]  URL didn't change (still {current_url}).")
            
        if not is_on_results_page:
            first_page_url = build_search_url(location_slug, keyword, min_size, listing_type, 1)
            print(f"  [INFO]  Homepage UI search failed. Forcing direct navigation as fallback...")
            try:
                driver.get(first_page_url)
                human_delay(2000, 4000)
            except Exception as e:
                print(f"  [ERROR]  Direct navigation failed: {e}")
        else:
            apply_filters_on_results_page(driver, keyword)

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
                url = build_search_url(location_slug, keyword, min_size, listing_type, page_num)
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

    except Exception as e:
        print(f"  [ERROR]  Critical scraper failure: {e}")
    finally:
        print("  [INFO]  Closing browser...")
        driver.quit()

    return all_listings
'''

with open('scraper.py', 'w', encoding='utf-8') as f:
    f.write(new_scraper)

print("scraper.py rewritten successfully!")
