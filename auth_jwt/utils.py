from typing import Optional, Dict, Any
from django.db import connection
from passlib.hash import bcrypt, argon2

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    sql = """
      SELECT id, email, COALESCE(name, ''), password, email_verified_at
      FROM users
      WHERE lower(email) = lower(%s)
      LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [email])
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "password": row[3], "email_verified_at": row[4]}

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT id, email, COALESCE(name, '') FROM users WHERE id = %s LIMIT 1"
    with connection.cursor() as cur:
        cur.execute(sql, [user_id])
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2]}

def verify_laravel_password(plain: str, hashed: str) -> bool:
    try:
        if hashed.startswith("$argon2"):
            return argon2.verify(plain, hashed)
        return bcrypt.verify(plain, hashed)  # покрывает $2y$, $2b$, $2a$
    except Exception:
        return False