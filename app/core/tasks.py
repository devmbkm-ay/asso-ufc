"""
Scheduled tasks — APScheduler (BackgroundScheduler).
The scheduler is started/stopped via the FastAPI lifespan.
"""
import logging
from datetime import date, datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core import email as email_svc

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


# ── Tâche : rappels cotisations ───────────────────────────────────────────────

def send_overdue_reminders() -> None:
    """
    Envoie un rappel email aux membres actifs sans paiement confirmé
    pour le mois courant. Exécutée automatiquement le REMINDER_DAY du mois.
    """
    from app.core.database import SessionLocal
    from models import Member, MemberStatus, Notification, NotificationType, Payment, PaymentStatus

    today = date.today()
    month, year = today.month, today.year
    logger.info("Cron rappels cotisations — %02d/%d", month, year)

    db = SessionLocal()
    try:
        active_members = db.query(Member).filter(
            Member.status == MemberStatus.active
        ).all()

        paid_ids = {
            row.member_id
            for row in db.query(Payment.member_id).filter(
                Payment.period_month == month,
                Payment.period_year  == year,
                Payment.status       == PaymentStatus.confirmed,
            ).all()
        }

        sent = failed = skipped = 0

        for member in active_members:
            if member.id in paid_ids:
                skipped += 1
                continue

            ok = email_svc.send_cotisation_reminder(
                to_email=member.email,
                first_name=member.first_name,
                month=month,
                year=year,
                amount=0,
            )
            now = datetime.now(tz=timezone.utc)
            db.add(Notification(
                id=uuid4(),
                member_id=member.id,
                type=NotificationType.cotisation_reminder,
                subject=f"Rappel cotisation — {month:02d}/{year}",
                body="",
                sent=ok,
                sent_at=now if ok else None,
            ))
            if ok:
                sent += 1
            else:
                failed += 1

        db.commit()
        logger.info(
            "Rappels terminés — envoyés: %d, échecs: %d, déjà payés: %d",
            sent, failed, skipped,
        )
    except Exception:
        logger.exception("Erreur lors des rappels cotisations")
        db.rollback()
    finally:
        db.close()


# ── Démarrage / arrêt ─────────────────────────────────────────────────────────

def start_scheduler() -> None:
    scheduler.add_job(
        send_overdue_reminders,
        trigger=CronTrigger(
            day=settings.REMINDER_DAY,
            hour=settings.REMINDER_HOUR,
            minute=0,
        ),
        id="cotisation_reminders",
        replace_existing=True,
        misfire_grace_time=3600,   # tolère 1h de retard (redémarrage conteneur)
    )
    scheduler.start()
    logger.info(
        "Scheduler démarré — rappels cotisations le %d du mois à %dh UTC",
        settings.REMINDER_DAY, settings.REMINDER_HOUR,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté")
