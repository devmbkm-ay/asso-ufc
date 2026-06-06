from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# ── Passwords ─────────────────────────────────────────────────────────────────
# bcrypt est un algorithme de hachage à sens unique conçu pour être lent
# (contrairement à MD5/SHA), ce qui rend les attaques par force brute peu
# pratiques même si la base de données est compromise.
# On utilise bcrypt directement (sans passlib) pour éviter les conflits
# de versions liés au check interne detect_wrap_bug de passlib.

def hash_password(plain: str) -> str:
    # Chaque appel produit un résultat différent grâce au salt aléatoire inclus.
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # Compare le mot de passe saisi avec le hash stocké sans jamais "déchiffrer".
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Tokens JWT ────────────────────────────────────────────────────────────────
# Un JWT (JSON Web Token) est une chaîne encodée en base64 qui contient des
# données lisibles ("payload") + une signature cryptographique.
# Le serveur vérifie la signature avec SECRET_KEY — sans consulter la BDD.
# Structure: header.payload.signature
# Payload type access : { sub: member_id, roles: [...], type: "access", exp: ... }

def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(member_id: UUID, roles: list[str]) -> str:
    # Token court (30 min par défaut) — utilisé pour chaque appel API.
    # Contient les rôles pour éviter une requête BDD à chaque vérification.
    return _create_token(
        {"sub": str(member_id), "roles": roles, "type": "access"},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(member_id: UUID) -> str:
    # Token long (7 jours par défaut) — utilisé uniquement pour obtenir
    # un nouvel access token. Ne contient pas les rôles intentionnellement.
    return _create_token(
        {"sub": str(member_id), "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Décode et valide un JWT.
    Lève JWTError si expiré ou signature invalide.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
