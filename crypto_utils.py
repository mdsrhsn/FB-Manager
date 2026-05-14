"""
FB Manager - Encryption Helper
==============================
Sensitive data (passwords, 2FA codes) ke liye Fernet encryption
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet


def get_encryption_key():
    """
    Encryption key environment variable se lo, ya derive karo SECRET_KEY se.
    Production mein FERNET_KEY set karen Railway env variables mein.
    """
    fernet_key = os.environ.get('FERNET_KEY')
    
    if fernet_key:
        try:
            # Validate karen ke yeh proper Fernet key hai
            Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
            return fernet_key.encode() if isinstance(fernet_key, str) else fernet_key
        except Exception:
            pass
    
    # Fallback: SECRET_KEY se derive karen (consistent rahega)
    secret = os.environ.get('SECRET_KEY', 'change-this-secret-in-production-12345')
    # SHA256 hash → 32 bytes → base64 → valid Fernet key
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


# Global cipher instance
_cipher = None


def get_cipher():
    """Lazy initialization of Fernet cipher"""
    global _cipher
    if _cipher is None:
        _cipher = Fernet(get_encryption_key())
    return _cipher


def encrypt_text(plain_text):
    """
    Plain text ko encrypt karen.
    Returns: encrypted base64 string, ya empty string agar input khali ho
    """
    if not plain_text:
        return ''
    try:
        cipher = get_cipher()
        encrypted = cipher.encrypt(str(plain_text).encode())
        return encrypted.decode()
    except Exception as e:
        print(f"⚠️ Encryption error: {e}")
        return ''


def decrypt_text(encrypted_text):
    """
    Encrypted text ko decrypt karen.
    Returns: original plain text, ya empty string agar fail ho
    """
    if not encrypted_text:
        return ''
    try:
        cipher = get_cipher()
        decrypted = cipher.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except Exception as e:
        # Backward compatibility — agar purana plain text hai to wahi return karen
        # (existing data ko break nahi karna)
        return str(encrypted_text)


def is_encrypted(text):
    """
    Check karen ke text encrypted hai ya plain.
    Fernet tokens 'gAAAAA' se start hote hain.
    """
    if not text:
        return False
    return str(text).startswith('gAAAAA')


def generate_new_key():
    """
    Naya Fernet key generate karen.
    Use this once: python -c "from utils.crypto import generate_new_key; print(generate_new_key())"
    """
    return Fernet.generate_key().decode()


if __name__ == '__main__':
    # Test
    test = "MySecretPassword123"
    enc = encrypt_text(test)
    dec = decrypt_text(enc)
    print(f"Plain:     {test}")
    print(f"Encrypted: {enc}")
    print(f"Decrypted: {dec}")
    print(f"Match:     {test == dec}")
    print(f"\nGenerate new key for Railway:")
    print(f"FERNET_KEY={generate_new_key()}")
