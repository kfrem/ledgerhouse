import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


ENCRYPTED_PREFIX = "enc:"


def _fernet_key():
    configured_key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if configured_key:
        return configured_key.encode("ascii")

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_text(value):
    if value in (None, ""):
        return value
    value = str(value)
    if value.startswith(ENCRYPTED_PREFIX):
        return value
    token = Fernet(_fernet_key()).encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_text(value):
    if value in (None, ""):
        return value
    value = str(value)
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    token = value[len(ENCRYPTED_PREFIX):].encode("ascii")
    try:
        return Fernet(_fernet_key()).decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Encrypted field could not be decrypted with the configured key.") from exc


class EncryptedTextField(models.TextField):
    description = "TextField encrypted before database storage"

    def from_db_value(self, value, expression, connection):
        return decrypt_text(value)

    def to_python(self, value):
        return decrypt_text(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_text(value)
