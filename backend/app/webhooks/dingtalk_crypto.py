import base64
import hashlib
import logging
import struct
from typing import Dict, Optional

from Crypto.Cipher import AES

logger = logging.getLogger(__name__)


class DingTalkWebhookError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DingTalkCallbackCrypto:
    """DingTalk HTTP callback signature verification and AES decryption."""

    def __init__(self, token: str, encoding_aes_key: str, owner_key: str):
        if not token or not encoding_aes_key or not owner_key:
            raise DingTalkWebhookError("Webhook crypto requires token, encoding_aes_key, and owner_key")
        if len(encoding_aes_key) != 43:
            raise DingTalkWebhookError("encoding_aes_key must be 43 characters")
        self.token = token
        self.owner_key = owner_key
        self.aes_key = base64.b64decode(encoding_aes_key + "=")

    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> None:
        expected = self._compute_signature(timestamp, nonce, encrypt)
        if expected != msg_signature:
            logger.warning("DingTalk webhook signature mismatch")
            raise DingTalkWebhookError("Invalid webhook signature")

    def decrypt(self, encrypt: str) -> str:
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        decrypted = cipher.decrypt(base64.b64decode(encrypt))
        pad = decrypted[-1]
        if pad < 1 or pad > 32:
            raise DingTalkWebhookError("Invalid AES padding")
        content = decrypted[:-pad]
        msg_len = struct.unpack(">I", content[16:20])[0]
        message = content[20 : 20 + msg_len].decode("utf-8")
        from_corp = content[20 + msg_len :].decode("utf-8")
        if from_corp != self.owner_key:
            raise DingTalkWebhookError("Webhook owner key mismatch")
        return message

    def encrypt(self, plaintext: str) -> str:
        random_bytes = hashlib.sha256(plaintext.encode()).digest()[:16]
        msg_bytes = plaintext.encode("utf-8")
        owner_bytes = self.owner_key.encode("utf-8")
        content = random_bytes + struct.pack(">I", len(msg_bytes)) + msg_bytes + owner_bytes
        pad_len = 32 - (len(content) % 32)
        content += bytes([pad_len]) * pad_len
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        return base64.b64encode(cipher.encrypt(content)).decode("utf-8")

    def get_encrypted_response(self, plaintext: str = "success") -> Dict[str, str]:
        import secrets
        import time

        encrypt = self.encrypt(plaintext)
        timestamp = str(int(time.time() * 1000))
        nonce = secrets.token_hex(8)
        signature = self._compute_signature(timestamp, nonce, encrypt)
        return {
            "msg_signature": signature,
            "timeStamp": timestamp,
            "nonce": nonce,
            "encrypt": encrypt,
        }

    def _compute_signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        parts = sorted([self.token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()
