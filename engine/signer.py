"""Signature des transactions avec cles chiffrees."""
import os
from cryptography.fernet import Fernet


class Signer:
    def __init__(self, keystore_path: str):
        self.keystore_path = keystore_path
        password = os.environ.get("MCAD_KEYSTORE_PASSWORD")
        if not password:
            raise RuntimeError("MCAD_KEYSTORE_PASSWORD manquant")
        self.fernet = Fernet(password.encode())

    def load(self) -> str:
        with open(self.keystore_path, "rb") as f:
            return self.fernet.decrypt(f.read()).decode()

    def save(self, data: str):
        token = self.fernet.encrypt(data.encode())
        with open(self.keystore_path, "wb") as f:
            f.write(token)
