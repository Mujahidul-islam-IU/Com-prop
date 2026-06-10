import os
import json
import config

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enquiry_settings.json")

def get_enquiry_settings():
    """
    Reads the enquiry settings from the JSON file.
    If the file doesn't exist, falls back to values in config.py.
    """
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "name": data.get("name", config.ENQUIRY_NAME),
                    "email": data.get("email", config.ENQUIRY_EMAIL),
                    "phone": data.get("phone", config.ENQUIRY_PHONE),
                    "template": data.get("template", config.ENQUIRY_MESSAGE_TEMPLATE)
                }
        except Exception as e:
            print(f"Error reading enquiry settings: {e}")

    # Fallback to config.py defaults
    return {
        "name": config.ENQUIRY_NAME,
        "email": config.ENQUIRY_EMAIL,
        "phone": config.ENQUIRY_PHONE,
        "template": config.ENQUIRY_MESSAGE_TEMPLATE
    }

def save_enquiry_settings(name: str, email: str, phone: str, template: str):
    """
    Saves the enquiry settings to the JSON file.
    """
    settings = {
        "name": name,
        "email": email,
        "phone": phone,
        "template": template
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
    return True
