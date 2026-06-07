from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireSecretary
from app.schemas.event import (
    AttendanceReport, EventCreate, EventRead, EventUpdate,
    RegistrationCreate, RegistrationRead,
)
from models import Event, EventRegistration, EventStatus, Member, MemberStatus

router = APIRouter(tags=["Événements"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_to_read(e: Event) -> EventRead:
    return EventRead(
        id=e.id,
        title=e.title,
        description=e.description,
        event_date=e.event_date,
        location=e.location,
        capacity=e.capacity,
        ticket_price=e.ticket_price,
        status=e.status.value,
        created_by=e.created_by,
        created_at=e.created_at,
        registrations_count=len(e.registrations),
    )


def _reg_to_read(r: EventRegistration) -> RegistrationRead:
    return RegistrationRead(
        id=r.id,
        event_id=r.event_id,
        member_id=r.member_id,
        member_name=f"{r.member.first_name} {r.member.last_name}",
        attended=r.attended,
        amount_paid=r.amount_paid,
        registered_at=r.registered_at,
    )


def _get_event_or_404(event_id: UUID, db: Session) -> Event:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    return event


# ── Événements ────────────────────────────────────────────────────────────────

@router.get("/events", response_model=list[EventRead],
            summary="Liste des événements")
def list_events(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    upcoming_only: bool = Query(False),
    event_status: Optional[str] = Query(None, alias="status",
                                        pattern="^(draft|published|cancelled|completed)$"),
):
    q = db.query(Event)
    if upcoming_only:
        q = q.filter(Event.event_date >= date.today())
    if event_status:
        q = q.filter(Event.status == event_status)
    events = q.order_by(Event.event_date.asc()).all()
    return [_event_to_read(e) for e in events]


@router.post("/events", response_model=EventRead,
             status_code=status.HTTP_201_CREATED,
             summary="Créer un événement")
def create_event(
    payload: EventCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    event = Event(
        id=uuid4(),
        created_by=current_member.id,
        **payload.model_dump(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_to_read(event)


@router.get("/events/{event_id}", response_model=EventRead,
            summary="Détail d'un événement")
def get_event(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    return _event_to_read(_get_event_or_404(event_id, db))


@router.patch("/events/{event_id}", response_model=EventRead,
              summary="Modifier un événement")
def update_event(
    event_id: UUID,
    payload: EventUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    event = _get_event_or_404(event_id, db)
    if event.status == EventStatus.cancelled:
        raise HTTPException(status_code=409, detail="Impossible de modifier un événement annulé")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return _event_to_read(event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Annuler un événement")
def cancel_event(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    event = _get_event_or_404(event_id, db)
    event.status = EventStatus.cancelled
    db.commit()


# ── Inscriptions ──────────────────────────────────────────────────────────────

@router.get("/events/my-registrations", response_model=list[RegistrationRead],
            summary="Mes inscriptions à des événements")
def my_registrations(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    regs = (
        db.query(EventRegistration)
        .filter(EventRegistration.member_id == current_member.id)
        .all()
    )
    return [_reg_to_read(r) for r in regs]


@router.get("/events/{event_id}/my-registration", response_model=Optional[RegistrationRead],
            summary="Mon inscription à un événement")
def my_registration(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    reg = db.query(EventRegistration).filter(
        EventRegistration.event_id == event_id,
        EventRegistration.member_id == current_member.id,
    ).first()
    return _reg_to_read(reg) if reg else None


@router.post("/events/{event_id}/registrations", response_model=RegistrationRead,
             status_code=status.HTTP_201_CREATED,
             summary="Inscrire un membre à un événement")
def register_member(
    event_id: UUID,
    payload: RegistrationCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    event = _get_event_or_404(event_id, db)
    if event.status != EventStatus.published:
        raise HTTPException(status_code=409, detail="Les inscriptions ne sont ouvertes que pour les événements publiés")

    member = db.query(Member).filter(Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    if event.capacity is not None and len(event.registrations) >= event.capacity:
        raise HTTPException(status_code=409, detail="Capacité maximale atteinte")

    existing = db.query(EventRegistration).filter(
        EventRegistration.event_id == event_id,
        EventRegistration.member_id == payload.member_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ce membre est déjà inscrit")

    reg = EventRegistration(
        id=uuid4(),
        event_id=event_id,
        member_id=payload.member_id,
        amount_paid=payload.amount_paid,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return _reg_to_read(reg)


@router.delete("/events/{event_id}/registrations/{registration_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Se désinscrire d'un événement")
def unregister(
    event_id: UUID,
    registration_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Un membre peut se désinscrire de sa propre inscription."""
    reg = db.query(EventRegistration).filter(
        EventRegistration.id == registration_id,
        EventRegistration.event_id == event_id,
        EventRegistration.member_id == current_member.id,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Inscription introuvable")
    db.delete(reg)
    db.commit()


@router.get("/events/{event_id}/registrations", response_model=list[RegistrationRead],
            summary="Liste des inscrits")
def list_registrations(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    event = _get_event_or_404(event_id, db)
    return [_reg_to_read(r) for r in event.registrations]


@router.post("/events/{event_id}/registrations/{registration_id}/checkin",
             response_model=RegistrationRead,
             summary="Marquer un membre comme présent")
def checkin(
    event_id: UUID,
    registration_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    reg = db.query(EventRegistration).filter(
        EventRegistration.id == registration_id,
        EventRegistration.event_id == event_id,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Inscription introuvable")
    if reg.attended:
        raise HTTPException(status_code=409, detail="Ce membre a déjà été marqué présent")
    reg.attended = True
    db.commit()
    db.refresh(reg)
    return _reg_to_read(reg)


# ── Rapport de présence ───────────────────────────────────────────────────────

@router.get("/events/{event_id}/attendance", response_model=AttendanceReport,
            summary="Rapport de présence")
def attendance_report(
    event_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    event = _get_event_or_404(event_id, db)
    regs = event.registrations

    total_registered = len(regs)
    total_attended   = sum(1 for r in regs if r.attended)
    total_revenue    = sum(r.amount_paid for r in regs)
    rate = round(total_attended / total_registered * 100, 1) if total_registered else 0.0

    return AttendanceReport(
        event_id=event.id,
        event_title=event.title,
        event_date=event.event_date,
        total_registered=total_registered,
        total_attended=total_attended,
        attendance_rate=rate,
        total_revenue=total_revenue,
        registrations=[_reg_to_read(r) for r in regs],
    )
