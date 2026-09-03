import logging
import razorpay
from typing import Dict, Any, Optional
import config

logger = logging.getLogger("merchant_agent.razorpay")

class RazorpayClientWrapper:
    """
    Thin wrapper around Razorpay Payment Links API (Test Mode).
    Handles real Razorpay API interactions when credentials are set in .env,
    or transparent fallback to mock test mode if placeholders are used.
    """

    def __init__(self):
        self.key_id = config.RAZORPAY_KEY_ID
        self.key_secret = config.RAZORPAY_KEY_SECRET
        self.is_mock = (
            not self.key_id 
            or "placeholder" in self.key_id.lower() 
            or "yourkey" in self.key_id.lower()
        )

        if not self.is_mock:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            logger.info("Razorpay Client initialized with provided API keys.")
        else:
            self.client = None
            logger.info("Razorpay Client running in MOCK mode (set real keys in .env for live test mode calls).")

    def create_payment_link(
        self, 
        order_id: str, 
        amount_inr: float, 
        product_name: str, 
        buyer_agent_id: str
    ) -> Dict[str, Any]:
        """
        Creates a Razorpay Payment Link for the specified order.
        Amount is converted to paise (1 INR = 100 paise).
        """
        amount_paise = int(round(amount_inr * 100))
        description = f"Order {order_id} - {product_name} via Agentic Commerce"

        if self.is_mock:
            # Mock mode response matching Razorpay Payment Link schema
            mock_id = f"plink_mock_{order_id}"
            mock_short_url = f"https://rzp.io/i/mock_{order_id}"
            return {
                "id": mock_id,
                "short_url": mock_short_url,
                "status": "created",
                "amount": amount_paise,
                "currency": config.MERCHANT_CURRENCY,
                "description": description,
                "reference_id": order_id,
                "is_mock": True
            }

        payload = {
            "amount": amount_paise,
            "currency": config.MERCHANT_CURRENCY,
            "accept_partial": False,
            "description": description,
            "reference_id": order_id,
            "notes": {
                "buyer_agent_id": buyer_agent_id,
                "merchant": config.MERCHANT_NAME,
                "channel": "MCP_Agentic_Commerce"
            },
            "callback_url": "https://example.com/payment-callback",
            "callback_method": "get"
        }

        try:
            response = self.client.payment_link.create(payload)
            return {
                "id": response.get("id"),
                "short_url": response.get("short_url"),
                "status": response.get("status"),
                "amount": response.get("amount"),
                "currency": response.get("currency"),
                "description": response.get("description"),
                "reference_id": response.get("reference_id"),
                "is_mock": False
            }
        except Exception as e:
            logger.error(f"Error creating Razorpay payment link: {str(e)}")
            raise RuntimeError(f"Razorpay API error: {str(e)}")

    def fetch_payment_link_status(self, razorpay_link_id: str) -> str:
        """
        Fetches current status of a payment link from Razorpay.
        Possible statuses: 'created', 'partially_paid', 'paid', 'expired', 'cancelled'
        """
        if self.is_mock or razorpay_link_id.startswith("plink_mock_"):
            return "created"

        try:
            response = self.client.payment_link.fetch(razorpay_link_id)
            return response.get("status", "unknown")
        except Exception as e:
            logger.error(f"Error fetching status for payment link {razorpay_link_id}: {str(e)}")
            return "unknown"
