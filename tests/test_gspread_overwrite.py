import sys
import os
import time

# Add backend directory to the path so we can import enquiry_agent and config
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from enquiry_agent import EnquiryAgent

def main():
    print("Initializing EnquiryAgent...")
    agent = EnquiryAgent()
    
    if not agent.sheet:
        print("Error: Could not connect to Google Sheets.")
        return
        
    print("\n--- Current Sheet State ---")
    all_vals = agent.sheet.get_all_values()
    initial_count = len(all_vals)
    print(f"Initial non-empty row count: {initial_count}")
    if initial_count > 0:
        print(f"Last row in sheet (Row {initial_count}): {all_vals[-1][:4]}...")

    # Mock listings to log
    test_listings = [
        {
            "title": "Mock Property X - Test 1",
            "address": "100 Test St, Melbourne VIC 3000",
            "price": "$50,000 net pa",
            "propertyType": "Office",
            "size": "150 sqm",
            "agent": "Test Agent A",
            "agency": "Test Agency A",
            "link": "https://www.commercialrealestate.com.au/property/test-x-1",
            "image": "https://example.com/img1.png",
            "tags": ["Office", "Modern"],
            "page_num": 1,
            "location_query": "Melbourne Region VIC"
        },
        {
            "title": "Mock Property Y - Test 2",
            "address": "200 Test St, Melbourne VIC 3000",
            "price": "$75,000 net pa",
            "propertyType": "Industrial",
            "size": "300 sqm",
            "agent": "Test Agent B",
            "agency": "Test Agency B",
            "link": "https://www.commercialrealestate.com.au/property/test-y-2",
            "image": "https://example.com/img2.png",
            "tags": ["Industrial", "Warehouse"],
            "page_num": 1,
            "location_query": "Melbourne Region VIC"
        }
    ]

    print("\n--- Simulating Scraper Logging ---")
    for idx, listing in enumerate(test_listings):
        print(f"\nProcessing property {idx + 1}/{len(test_listings)}: {listing['title']}")
        detail_info = {"property_id": f"999999{idx}"}
        message = f"Hi, I would like to enquire about {listing['title']}. Please provide more details."
        
        # Log to sheet
        agent.log_to_sheet(listing, detail_info, message, "Success")
        time.sleep(1) # Small pause
        
    print("\n--- Verifying Sheet State After Operations ---")
    all_vals_after = agent.sheet.get_all_values()
    final_count = len(all_vals_after)
    print(f"Final non-empty row count: {final_count}")
    
    # Print the newly appended rows to verify they are separate rows and have not overwritten anything
    print(f"Row {initial_count}: {all_vals_after[initial_count - 1][:4] if initial_count <= len(all_vals_after) else 'N/A'}...")
    for r in range(initial_count + 1, final_count + 1):
        print(f"Row {r} (Appended): {all_vals_after[r - 1][:4]}...")
        
    # Clean up test rows so we don't mess up the user's sheet
    if final_count > initial_count:
        print(f"\nCleaning up {final_count - initial_count} test rows from the sheet...")
        agent.sheet.delete_rows(initial_count + 1, final_count)
        print("Sheet successfully restored to original clean state.")

if __name__ == "__main__":
    main()
