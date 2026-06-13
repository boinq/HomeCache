import os


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

DEFAULT_CATEGORIES = [
    "food",
    "cleaning",
    "medicine",
    "tools",
    "electronics",
    "clothing",
    "documents",
    "other",
]

NTFY_SETTING_DEFAULTS = {
    "base_url": BASE_URL,
    "theme": "dark-green",
    "ntfy_enabled": "false",
    "ntfy_server_url": "https://ntfy.sh",
    "ntfy_topic": "",
    "ntfy_access_token": "",
    "ntfy_expiry_days": "7",
}

NTFY_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
