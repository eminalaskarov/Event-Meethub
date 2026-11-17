import base64
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

QR_PREFIX = "EH1."
CURRENT_KEY_VERSION = 1
NONCE_BYTES = 12
TICKET_ID_BYTES = 16
GCM_TAG_BYTES = 16
PACKED_BYTES = 1 + NONCE_BYTES + TICKET_ID_BYTES + GCM_TAG_BYTES
MAX_ENCODED_LENGTH = 128

_cipher = AESGCM(settings.qr_key_bytes)


def _associated_data(key_version: int) -> bytes:
    return b"event-meetup-hub:ticket-qr:" + bytes([key_version])


def encrypt_ticket_qr(ticket_id: UUID, nonce: bytes, key_version: int) -> str:
    """Build a stable payload. Each DB nonce is unique to one fixed ticket ID."""
    if key_version != CURRENT_KEY_VERSION:
        raise ValueError(f"Unsupported QR key version: {key_version}")

    nonce = bytes(nonce)
    if len(nonce) != NONCE_BYTES:
        raise ValueError("QR nonce must be 12 bytes")

    encrypted = _cipher.encrypt(nonce, ticket_id.bytes, _associated_data(key_version))
    packed = bytes([key_version]) + nonce + encrypted
    encoded = base64.urlsafe_b64encode(packed).rstrip(b"=").decode("ascii")
    return f"{QR_PREFIX}{encoded}"


def decrypt_ticket_qr(payload: str) -> UUID | None:
    """Return the ticket ID, or None for malformed or tampered payloads."""
    if not payload.startswith(QR_PREFIX):
        return None

    encoded = payload.removeprefix(QR_PREFIX)
    if len(encoded) > MAX_ENCODED_LENGTH:
        return None

    try:
        padding = "=" * (-len(encoded) % 4)
        packed = base64.b64decode(f"{encoded}{padding}", altchars=b"-_", validate=True)
    except ValueError:
        return None

    if len(packed) != PACKED_BYTES or packed[0] != CURRENT_KEY_VERSION:
        return None

    key_version = packed[0]
    nonce = packed[1:1 + NONCE_BYTES]
    encrypted = packed[1 + NONCE_BYTES:]

    try:
        ticket_bytes = _cipher.decrypt(nonce, encrypted, _associated_data(key_version))
    except InvalidTag:
        return None

    return UUID(bytes=ticket_bytes)