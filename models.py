"""
Association management — SQLAlchemy models
All tables use UUID primary keys and PostgreSQL-native types.
"""
import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ── Base ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    # Classe parente de tous les modèles — SQLAlchemy en a besoin pour
    # générer les tables PostgreSQL automatiquement via Alembic.
    pass


# ── Enums ────────────────────────────────────────────────────────────────────
# Un Enum définit une liste fermée de valeurs autorisées pour un champ.
# "str, enum.Enum" signifie que les valeurs sont aussi des chaînes Python
# normales, ce qui simplifie la sérialisation JSON.

class MemberStatus(str, enum.Enum):
    active    = "active"
    inactive  = "inactive"
    suspended = "suspended"
    honorary  = "honorary"
    # Compte créé via un lien/code d'adhésion public, en attente de
    # validation par un admin avant de devenir un membre à part entière.
    pending   = "pending"


class RoleName(str, enum.Enum):
    super_admin = "super_admin"
    president   = "president"
    treasurer   = "treasurer"
    secretary   = "secretary"
    member      = "member"


class CotisationFrequency(str, enum.Enum):
    monthly   = "monthly"
    annual    = "annual"
    one_time  = "one_time"


class PaymentMethod(str, enum.Enum):
    cash          = "cash"
    bank_transfer = "bank_transfer"
    lydia         = "lydia"
    sumeria       = "sumeria"
    wero          = "wero"
    other         = "other"


class PaymentStatus(str, enum.Enum):
    pending   = "pending"
    declared  = "declared"   # membre a déclaré avoir réglé, attente validation trésorier
    confirmed = "confirmed"
    cancelled = "cancelled"


class EventStatus(str, enum.Enum):
    draft     = "draft"
    published = "published"
    cancelled = "cancelled"
    completed = "completed"


class NotificationType(str, enum.Enum):
    cotisation_reminder = "cotisation_reminder"
    event_invitation    = "event_invitation"
    general             = "general"
    welcome             = "welcome"


# ── Tables ───────────────────────────────────────────────────────────────────
# Chaque classe représente une table en base de données.
# Column(type, ...) décrit une colonne :
#   nullable=False → valeur obligatoire
#   unique=True    → deux lignes ne peuvent pas avoir la même valeur
#   index=True     → crée un index pour accélérer les recherches
#   default=...    → valeur par défaut si non fournie
# ForeignKey("table.colonne") crée une clé étrangère (lien entre tables).

class Member(Base):
    __tablename__ = "members"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    phone         = Column(String(30))
    address       = Column(String(500))
    birth_date    = Column(Date)
    joined_at     = Column(Date, nullable=False, default=date.today)
    status        = Column(Enum(MemberStatus), nullable=False, default=MemberStatus.active, index=True)
    # Auto-référence : qui a créé ce membre (un autre membre de l'asso)
    created_by    = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # onupdate=func.now() : mis à jour automatiquement à chaque modification
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Les relationships permettent d'accéder aux objets liés via Python
    # (ex: member.payments retourne tous les paiements de ce membre)
    # sans écrire de JOIN SQL manuellement.
    roles         = relationship("MemberRole", back_populates="member", foreign_keys="MemberRole.member_id")
    payments      = relationship("Payment", back_populates="member", foreign_keys="Payment.member_id")
    registrations = relationship("EventRegistration", back_populates="member")
    notifications = relationship("Notification", back_populates="member")


class Role(Base):
    __tablename__ = "roles"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(Enum(RoleName), nullable=False, unique=True)
    description = Column(String(500))

    members = relationship("MemberRole", back_populates="role")


class MemberRole(Base):
    # Table de liaison entre Member et Role (relation many-to-many).
    # Un membre peut avoir plusieurs rôles, un rôle peut être attribué
    # à plusieurs membres.
    __tablename__ = "member_roles"
    __table_args__ = (
        # Contrainte d'unicité : un même rôle ne peut pas être attribué
        # deux fois au même membre.
        UniqueConstraint("member_id", "role_id", name="uq_member_role"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ondelete="CASCADE" : si le membre est supprimé, ses rôles le sont aussi
    member_id   = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id     = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    member = relationship("Member", back_populates="roles", foreign_keys=[member_id])
    role   = relationship("Role", back_populates="members")


class CotisationPlan(Base):
    __tablename__ = "cotisation_plans"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label       = Column(String(200), nullable=False)
    # Numeric(10, 2) : nombre décimal avec 10 chiffres au total et 2 après la virgule
    amount      = Column(Numeric(10, 2), nullable=False)
    frequency   = Column(Enum(CotisationFrequency), nullable=False, default=CotisationFrequency.annual)
    valid_from  = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True, index=True)

    payments = relationship("Payment", back_populates="cotisation_plan")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        # Empêche de saisir deux paiements pour le même membre,
        # le même plan, le même mois et la même année.
        UniqueConstraint("member_id", "cotisation_plan_id", "period_month", "period_year",
                         name="uq_payment_period"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id          = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    cotisation_plan_id = Column(UUID(as_uuid=True), ForeignKey("cotisation_plans.id"), nullable=False)
    amount             = Column(Numeric(10, 2), nullable=False)
    payment_date       = Column(Date, nullable=False, default=date.today)
    period_month       = Column(Integer, nullable=True)   # 1-12, null pour annual/one_time
    period_year        = Column(Integer, nullable=False)
    method             = Column(Enum(PaymentMethod), nullable=False, default=PaymentMethod.cash)
    status             = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.confirmed, index=True)
    reference          = Column(String(200))
    recorded_by        = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    notes              = Column(Text)

    member          = relationship("Member", back_populates="payments", foreign_keys=[member_id])
    cotisation_plan = relationship("CotisationPlan", back_populates="payments")


class Event(Base):
    __tablename__ = "events"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title        = Column(String(300), nullable=False)
    description  = Column(Text)
    event_date   = Column(Date, nullable=False, index=True)
    location     = Column(String(500))
    capacity     = Column(Integer)
    ticket_price = Column(Numeric(10, 2), nullable=False, default=0)
    status       = Column(Enum(EventStatus), nullable=False, default=EventStatus.draft, index=True)
    created_by   = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    registrations = relationship("EventRegistration", back_populates="event")


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = (
        # Un membre ne peut s'inscrire qu'une seule fois par événement.
        UniqueConstraint("event_id", "member_id", name="uq_event_member"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id      = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id     = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    attended      = Column(Boolean, nullable=False, default=False)
    amount_paid   = Column(Numeric(10, 2), nullable=False, default=0)
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event  = relationship("Event", back_populates="registrations")
    member = relationship("Member", back_populates="registrations")


class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id  = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    type       = Column(Enum(NotificationType), nullable=False)
    subject    = Column(String(500), nullable=False)
    body       = Column(Text, nullable=False)
    sent       = Column(Boolean, nullable=False, default=False, index=True)
    sent_at    = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    member = relationship("Member", back_populates="notifications")


class AuditLog(Base):
    # Journal immuable — on n'y écrit, jamais on ne modifie ni supprime.
    __tablename__ = "audit_logs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id   = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    action     = Column(String(100), nullable=False)   # ex: "payment.create", "member.update"
    table_name = Column(String(100), nullable=False)
    record_id  = Column(UUID(as_uuid=True), nullable=True)
    diff       = Column(JSONB)                         # {"before": {...}, "after": {...}}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Collecte(Base):
    # Collecte de solidarité déclenchée au décès d'un proche d'un membre.
    __tablename__ = "collectes"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title            = Column(String(300), nullable=False)
    beneficiary_name = Column(String(200), nullable=False)
    photo_url        = Column(String(500))
    description      = Column(Text)
    min_amount       = Column(Numeric(10, 2), nullable=False, default=20.00)
    goal_amount      = Column(Numeric(10, 2), nullable=True)
    start_date       = Column(Date, nullable=False)
    # end_date = start_date + 14 jours, calculé à la création
    end_date         = Column(Date, nullable=False)
    is_closed        = Column(Boolean, nullable=False, default=False)
    is_archived      = Column(Boolean, nullable=False, default=False)
    archived_at      = Column(DateTime(timezone=True), nullable=True)
    category         = Column(String(50), nullable=True)  # deces|mariage|naissance|maladie|autre
    created_by       = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    contributions = relationship("Contribution", back_populates="collecte")


class Contribution(Base):
    # Participation d'un membre à une collecte de solidarité.
    __tablename__ = "contributions"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collecte_id    = Column(UUID(as_uuid=True), ForeignKey("collectes.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id      = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    amount         = Column(Numeric(10, 2), nullable=False)
    is_anonymous   = Column(Boolean, nullable=False, default=False)
    method         = Column(Enum(PaymentMethod), nullable=False, default=PaymentMethod.other)
    status         = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.pending, index=True)
    reference      = Column(String(200))
    recorded_by    = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    contributed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    collecte = relationship("Collecte", back_populates="contributions")
    member   = relationship("Member", foreign_keys=[member_id])


class MemberInvite(Base):
    __tablename__ = "member_invites"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email      = Column(String(255), nullable=False, index=True)
    token      = Column(String(64), nullable=False, unique=True, index=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class JoinCode(Base):
    # Code d'adhésion réutilisable : contrairement à MemberInvite (un token
    # à usage unique par email), un même code peut être partagé et utilisé
    # par plusieurs personnes tant qu'il est actif et non expiré.
    __tablename__ = "join_codes"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code       = Column(String(16), nullable=False, unique=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False)
    is_active  = Column(Boolean, nullable=False, default=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id  = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False, index=True)
    token      = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    member = relationship("Member")
