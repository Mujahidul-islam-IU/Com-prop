import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time

options = uc.ChromeOptions()
options.add_argument("--disable-popup-blocking")
driver = uc.Chrome(options=options, use_subprocess=True, version_main=148)

try:
    print("Loading URL...")
    driver.get("https://www.commercialrealestate.com.au/property/759-springvale-road-mulgrave-vic-3170-18052887")
    time.sleep(5)
    
    # Try to find something that says Property ID
    els = driver.find_elements(By.XPATH, '//*[contains(text(), "Property ID")]/..')
    print(f"Found {len(els)} elements containing 'Property ID'")
    for el in els:
        print("--- PARENT HTML ---")
        print(el.get_attribute('outerHTML'))

    # Also try to find Floor Area
    els2 = driver.find_elements(By.XPATH, '//*[contains(text(), "Floor Area")]/..')
    print(f"Found {len(els2)} elements containing 'Floor Area'")
    for el in els2:
        print("--- PARENT HTML ---")
        print(el.get_attribute('outerHTML'))
finally:
    driver.quit()
