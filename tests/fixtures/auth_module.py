"""Auth module — separate cluster from payments."""
import logging

logger = logging.getLogger(__name__)


class AuthService:

    def __init__(self, token_store):
        self.store = token_store

    def authenticate(self, token: str):
        if not token:
            raise ValueError("token required")
        record = self.store.find(token)
        logger.info("auth checked")
        return record

    def authorize(self, user, permission: str):
        if not user:
            raise PermissionError("no user")
        return self.store.get(f"perm:{user}:{permission}")

    def __del__(self):
        self.store = None


class TokenRepository:

    def find(self, token: str):
        return self.db.query(f"SELECT * FROM tokens WHERE value='{token}'")

    def save(self, token: str, user_id: str):
        self.db.insert({"token": token, "user_id": user_id})
