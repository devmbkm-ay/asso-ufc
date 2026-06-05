from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt est un algorithme de hachage à sens unique conçu pour être lent
# (contrairement à MD5/SHA), ce qui rend les attaques par force brute peu
# pratiques même si la base de données est compromise.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    # Transforme le mot de passe en une chaîne illisible stockée en BDD.
    # Chaque appel produit un résultat différent (salt aléatoire inclus).
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    # Compare le mot de passe saisi avec le hash stocké sans jamais
    # "déchiffrer" — bcrypt re-hache et compare les deux résultats.
    return pwd_context.verify(plain, hashed)


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
