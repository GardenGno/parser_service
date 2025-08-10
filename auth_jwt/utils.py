# auth_jwt/utils.py
from passlib.hash import bcrypt as passlib_bcrypt

def verify_laravel_password(raw_password: str, hashed_password: str) -> bool:
    """
    Проверяет bcrypt-хеши Laravel ($2y$...).
    """
    if not hashed_password:
        return False
    try:
        return passlib_bcrypt.verify(raw_password, hashed_password)
    except Exception:
        return False