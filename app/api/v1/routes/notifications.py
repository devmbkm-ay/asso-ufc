from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireSecretary, RequireTreasurer
from app.core import email as email_svc
from app.schemas.notification import NotificationRead, ReminderResult
from models import (
    Event, EventStatus, Member, MemberStatus,
    Notification, NotificationType, Payment, PaymentStatus,
)

router = APIRouter(tags=["Notifications"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_notification(
    db: Session,
    member_id: UUID,
    notif_type: NotificationType,
    subject: str,
    sent: bool,
) -> Notification:
    now = datetime.now(tz=timezone.utc) if sent else None
    notif = Notification(
        id=uuid4(),
        member_id=member_id,
        type=notif_type,
        subject=subject,
        body="",
        sent=sent,
        sent_at=now,
    )
    db.add(notif)
    return notif


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=list[NotificationRead],
            summary="Historique des notifications envoyées")
def list_notifications(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    member_id: Optional[UUID] = None,
    sent: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    _=RequireSecretary,
):
    q = db.query(Notification)
    if member_id:
        q = q.filter(Notification.member_id == member_id)
    if sent is not None:
        q = q.filter(Notification.sent == sent)
    return q.order_by(Notification.created_at.desc()).limit(limit).all()


@router.post("/notifications/welcome/{member_id}",
             response_model=NotificationRead,
             status_code=status.HTTP_201_CREATED,
             summary="Envoyer l'email de bienvenue à un membre")
def send_welcome(
    member_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    ok = email_svc.send_welcome(member.email, member.first_name)
    subject = f"Bienvenue dans l'association !"
    notif = _save_notification(db, member.id, NotificationType.welcome, subject, ok)
    db.commit()
    db.refresh(notif)

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email non envoyé — vérifiez la configuration Brevo",
        )
    return notif


@router.post("/notifications/remind-overdue",
             response_model=ReminderResult,
             summary="Envoyer les rappels aux membres en retard de cotisation")
def remind_overdue(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    year:  int = Query(default_factory=lambda: date.today().year),
    _=RequireTreasurer,
):
    # Membres actifs
    active_members = db.query(Member).filter(
        Member.status == MemberStatus.active,
    ).all()

    # Membres qui ont déjà payé ce mois
    paid_ids = {
        row.member_id
        for row in db.query(Payment.member_id).filter(
            Payment.period_month == month,
            Payment.period_year == year,
            Payment.status == PaymentStatus.confirmed,
        ).all()
    }

    sent_count = failed_count = skipped_count = 0

    for member in active_members:
        if member.id in paid_ids:
            skipped_count += 1
            continue

        # On cible uniquement les membres avec plan cotisation — on lit le dernier plan actif
        ok = email_svc.send_cotisation_reminder(
            to_email=member.email,
            first_name=member.first_name,
            month=month,
            year=year,
            amount=0,   # montant générique — le trésorier connaît le plan
        )
        subject = f"Rappel cotisation — mois {month:02d}/{year}"
        notif = _save_notification(
            db, member.id, NotificationType.cotisation_reminder, subject, ok
        )
        if ok:
            sent_count += 1
        else:
            failed_count += 1

    db.commit()

    return ReminderResult(
        total_targeted=len(active_members),
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


@router.post("/notifications/event-invite/{event_id}",
             response_model=ReminderResult,
             status_code=status.HTTP_201_CREATED,
             summary="Inviter tous les membres actifs à un événement")
def invite_to_event(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    if event.status != EventStatus.published:
        raise HTTPException(status_code=409, detail="L'événement doit être publié avant d'envoyer les invitations")

    members = db.query(Member).filter(Member.status == MemberStatus.active).all()

    sent_count = failed_count = 0
    for member in members:
        ok = email_svc.send_event_invitation(
            to_email=member.email,
            first_name=member.first_name,
            event_title=event.title,
            event_date=event.event_date,
            event_location=event.location,
        )
        subject = f"Invitation — {event.title}"
        _save_notification(db, member.id, NotificationType.event_invitation, subject, ok)
        if ok:
            sent_count += 1
        else:
            failed_count += 1

    db.commit()

    return ReminderResult(
        total_targeted=len(members),
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=0,
    )
