import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Razorpay Test Mode Credentials
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder_key")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "placeholder_secret")

# Merchant Guardrail Constraints
# Max order value allowed for automated AI agent checkout without human manual authorization
MERCHANT_MAX_ORDER_VALUE = float(os.getenv("MERCHANT_MAX_ORDER_VALUE", "5000.0"))

# Merchant Details
MERCHANT_NAME = "Bangalore Coffee Roasters"
MERCHANT_CURRENCY = "INR"

# File Paths
DATA_DIR = BASE_DIR / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
ORDERS_PATH = DATA_DIR / "orders.json"
AUDIT_LOG_PATH = BASE_DIR / "audit_log.jsonl"
