"""Sample Python fixture for Gate 1 testing."""
import logging
from abc import ABC

logger = logging.getLogger(__name__)


class PaymentService(ABC):

    def process_payment(self, amount: float, card_token: str):
        if not card_token:
            raise ValueError("card_token required")
        result = self.db.save({"amount": amount, "card": card_token})
        logger.info("payment saved")
        return result

    def __init__(self, db):
        self.db = db

    def __del__(self):
        self.db = None


class PaymentValidator:

    def validate(self, payload):
        if not isinstance(payload, dict):
            raise TypeError("payload must be dict")
        cleaned = {k: v.strip() for k, v in payload.items()}
        return cleaned


async def fetch_exchange_rate(currency: str):
    import asyncio
    await asyncio.sleep(0)
    return self.http.get(f"/rates/{currency}")


def top_level_helper():
    logger.debug("helper called")
