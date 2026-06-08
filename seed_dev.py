"""
Seeder de développement — crée des comptes de test si absents.

Usage :
    DATABASE_URL=postgresql://user:pass@localhost/asso_db python seed_dev.py

Comptes créés :
    super_admin  : admin@mboka.dev       / Admin1234
    treasurer    : tresorier@mboka.dev   / Tresor1234
    secretary    : secretaire@mboka.dev  / Secretaire1234
    member x3    : membre1..3@mboka.dev  / Membre1234
"""

import os
import sys
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    # Essai avec le .env local
    try:
        from dotenv import load_dotenv
        load_dotenv()
        DATABASE_URL = os.environ.get("DATABASE_URL")
    except ImportError:
        pass

if not DATABASE_URL:
    print("ERROR : DATABASE_URL non défini. Exemple :")
    print("  DATABASE_URL=postgresql://user:pass@localhost/asso_db python seed_dev.py")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

from app.core.security import hash_password
from models import Base, Member, MemberRole, Role, RoleName, MemberStatus

ACCOUNTS = [
    {
        "email":      "admin@mboka.dev",
        "first_name": "Admin",
        "last_name":  "Mboka",
        "password":   "Admin1234",
        "role":       RoleName.super_admin,
    },
    {
        "email":      "tresorier@mboka.dev",
        "first_name": "Jean",
        "last_name":  "Trésorier",
        "password":   "Tresor1234",
        "role":       RoleName.treasurer,
    },
    {
        "email":      "secretaire@mboka.dev",
        "first_name": "Marie",
        "last_name":  "Secrétaire",
        "password":   "Secretaire1234",
        "role":       RoleName.secretary,
    },
    {
        "email":      "membre1@mboka.dev",
        "first_name": "Awa",
        "last_name":  "Diallo",
        "password":   "Membre1234",
        "role":       RoleName.member,
    },
    {
        "email":      "membre2@mboka.dev",
        "first_name": "Brice",
        "last_name":  "Ntumba",
        "password":   "Membre1234",
        "role":       RoleName.member,
    },
    {
        "email":      "membre3@mboka.dev",
        "first_name": "Christelle",
        "last_name":  "Mbala",
        "password":   "Membre1234",
        "role":       RoleName.member,
    },
]


def seed():
    with Session(engine) as db:
        # Cherche le super_admin existant pour created_by
        existing_admin = (
            db.query(Member)
            .join(MemberRole, MemberRole.member_id == Member.id)
            .join(Role, Role.id == MemberRole.role_id)
            .filter(Role.name == RoleName.super_admin)
            .first()
        )
        creator_id = existing_admin.id if existing_admin else None

        created = 0
        skipped = 0

        for acc in ACCOUNTS:
            if db.query(Member).filter(Member.email == acc["email"]).first():
                print(f"  skip  {acc['email']} (déjà existant)")
                skipped += 1
                continue

            role = db.query(Role).filter(Role.name == acc["role"]).first()
            if not role:
                print(f"  WARN  rôle {acc['role']} introuvable — exécutez d'abord les migrations")
                continue

            member_id = uuid4()
            member = Member(
                id=member_id,
                first_name=acc["first_name"],
                last_name=acc["last_name"],
                email=acc["email"],
                password_hash=hash_password(acc["password"]),
                status=MemberStatus.active,
                joined_at=date.today(),
                created_by=creator_id or member_id,
            )
            db.add(member)
            db.flush()

            db.add(MemberRole(
                id=uuid4(),
                member_id=member.id,
                role_id=role.id,
                assigned_by=creator_id or member.id,
            ))

            # Le premier super_admin devient creator_id pour les suivants
            if creator_id is None and acc["role"] == RoleName.super_admin:
                creator_id = member.id

            print(f"  create {acc['email']}  [{acc['role'].value}]  mdp: {acc['password']}")
            created += 1

        db.commit()
        print(f"\nDone — {created} créé(s), {skipped} ignoré(s).")


if __name__ == "__main__":
    print("Seeder de développement Mboka\n")
    seed()
