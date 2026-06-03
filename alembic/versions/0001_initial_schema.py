"""Initial schema — 9 tables

Revision ID: 0001
Revises: 
Create Date: 2026-06-03

Tables created:
  members, roles, member_roles, cotisation_plans,
  payments, events, event_registrations, notifications, audit_logs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── members ──────────────────────────────────────────────────────────────
    op.create_table(
        "members",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("first_name", sa.String(100),  nullable=False),
        sa.Column("last_name",  sa.String(100),  nullable=False),
        sa.Column("email",      sa.String(255),  nullable=False),
        sa.Column("phone",      sa.String(30)),
        sa.Column("address",    sa.String(500)),
        sa.Column("birth_date", sa.Date),
        sa.Column("joined_at",  sa.Date,         nullable=False),
        sa.Column("status",
            sa.Enum("active", "inactive", "suspended", "honorary", name="memberstatus"),
            nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_members_email",  "members", ["email"],  unique=True)
    op.create_index("ix_members_status", "members", ["status"], unique=False)

    # ── roles ─────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id",   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name",
            sa.Enum("super_admin", "treasurer", "secretary", "member", name="rolename"),
            nullable=False, unique=True),
        sa.Column("description", sa.String(500)),
    )

    # ── member_roles ──────────────────────────────────────────────────────────
    op.create_table(
        "member_roles",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",   postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id",     postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.UniqueConstraint("member_id", "role_id", name="uq_member_role"),
    )
    op.create_index("ix_member_roles_member_id", "member_roles", ["member_id"])
    op.create_index("ix_member_roles_role_id",   "member_roles", ["role_id"])

    # ── cotisation_plans ──────────────────────────────────────────────────────
    op.create_table(
        "cotisation_plans",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label",       sa.String(200), nullable=False),
        sa.Column("amount",      sa.Numeric(10, 2), nullable=False),
        sa.Column("frequency",
            sa.Enum("monthly", "annual", "one_time", name="cotisationfrequency"),
            nullable=False, server_default="annual"),
        sa.Column("valid_from",  sa.Date, nullable=False),
        sa.Column("valid_until", sa.Date),
        sa.Column("is_active",   sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_cotisation_plans_is_active", "cotisation_plans", ["is_active"])

    # ── payments ──────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id",          postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id",          ondelete="CASCADE"), nullable=False),
        sa.Column("cotisation_plan_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cotisation_plans.id"), nullable=False),
        sa.Column("amount",       sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_date", sa.Date,           nullable=False),
        sa.Column("period_month", sa.Integer),
        sa.Column("period_year",  sa.Integer,        nullable=False),
        sa.Column("method",
            sa.Enum("cash", "bank_transfer", "lydia", "sumeria", "other", name="paymentmethod"),
            nullable=False, server_default="cash"),
        sa.Column("status",
            sa.Enum("pending", "confirmed", "cancelled", name="paymentstatus"),
            nullable=False, server_default="confirmed"),
        sa.Column("reference",   sa.String(200)),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("notes",       sa.Text),
        sa.UniqueConstraint(
            "member_id", "cotisation_plan_id", "period_month", "period_year",
            name="uq_payment_period"),
    )
    op.create_index("ix_payments_member_id", "payments", ["member_id"])
    op.create_index("ix_payments_status",    "payments", ["status"])

    # ── events ────────────────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title",        sa.String(300), nullable=False),
        sa.Column("description",  sa.Text),
        sa.Column("event_date",   sa.Date,        nullable=False),
        sa.Column("location",     sa.String(500)),
        sa.Column("capacity",     sa.Integer),
        sa.Column("ticket_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("status",
            sa.Enum("draft", "published", "cancelled", "completed", name="eventstatus"),
            nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_events_event_date", "events", ["event_date"])
    op.create_index("ix_events_status",     "events", ["status"])

    # ── event_registrations ───────────────────────────────────────────────────
    op.create_table(
        "event_registrations",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id",      postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("member_id",     postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attended",      sa.Boolean, nullable=False, server_default="false"),
        sa.Column("amount_paid",   sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_id", "member_id", name="uq_event_member"),
    )
    op.create_index("ix_event_registrations_event_id",  "event_registrations", ["event_id"])
    op.create_index("ix_event_registrations_member_id", "event_registrations", ["member_id"])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id",        postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type",
            sa.Enum("cotisation_reminder", "event_invitation", "general", "welcome",
                    name="notificationtype"),
            nullable=False),
        sa.Column("subject",    sa.String(500), nullable=False),
        sa.Column("body",       sa.Text,        nullable=False),
        sa.Column("sent",       sa.Boolean,     nullable=False, server_default="false"),
        sa.Column("sent_at",    sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_member_id", "notifications", ["member_id"])
    op.create_index("ix_notifications_sent",      "notifications", ["sent"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id",   postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"), nullable=True),
        sa.Column("action",     sa.String(100), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id",  postgresql.UUID(as_uuid=True)),
        sa.Column("diff",       postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # Suppression dans l'ordre inverse (respect des FK)
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("event_registrations")
    op.drop_table("events")
    op.drop_table("payments")
    op.drop_table("cotisation_plans")
    op.drop_table("member_roles")
    op.drop_table("roles")
    op.drop_table("members")

    # Suppression des types enum PostgreSQL
    sa.Enum(name="notificationtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="eventstatus").drop(op.get_bind(),      checkfirst=True)
    sa.Enum(name="paymentstatus").drop(op.get_bind(),    checkfirst=True)
    sa.Enum(name="paymentmethod").drop(op.get_bind(),    checkfirst=True)
    sa.Enum(name="cotisationfrequency").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="rolename").drop(op.get_bind(),         checkfirst=True)
    sa.Enum(name="memberstatus").drop(op.get_bind(),     checkfirst=True)
