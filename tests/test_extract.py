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
    
    try:
        area_val = driver.find_element(By.CSS_SELECTOR, 'td[data-testid*="highlights-row-value Floor Area"], td[data-testid*="highlights-row-value Building Area"], td[data-testid*="highlights-row-value Land Area"]')
        print("CSS SELECTOR Floor Area:", area_val.get_attribute('textContent').strip())
    except Exception as e:
        print("CSS SELECTOR Floor Area FAILED:", e)

    try:
        prop_id = driver.find_element(By.CSS_SELECTOR, 'td[data-testid*="highlights-row-value Property ID"]')
        print("CSS SELECTOR Property ID:", prop_id.get_attribute('textContent').strip())
    except Exception as e:
        print("CSS SELECTOR Property ID FAILED:", e)

finally:
    driver.quit()
