from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.schemas.search import SearchResultItem
from models import Collecte, Event, Member, RoleName

router = APIRouter(prefix="/search", tags=["Recherche globale"])

# Mêmes rôles que ceux qui voient déjà membres/événements/collectes côté admin.
RequireSearch = Depends(require_roles(
    RoleName.super_admin, RoleName.president, RoleName.treasurer, RoleName.secretary,
))

RESULTS_PER_TYPE = 5


@router.get("", response_model=list[SearchResultItem],
            summary="Recherche globale — membres, événements, collectes")
def global_search(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    _=RequireSearch,
):
    term = f"%{q.lower()}%"
    results: list[SearchResultItem] = []

    members = (
        db.query(Member)
        .filter(or_(
            func.lower(Member.first_name).like(term),
            func.lower(Member.last_name).like(term),
            func.lower(Member.email).like(term),
        ))
        .order_by(Member.last_name)
        .limit(RESULTS_PER_TYPE)
        .all()
    )
    results += [
        SearchResultItem(
            type="member", id=m.id,
            title=f"{m.first_name} {m.last_name}",
            subtitle=m.email,
            href=f"/membres/{m.id}",
        )
        for m in members
    ]

    events = (
        db.query(Event)
        .filter(func.lower(Event.title).like(term))
        .order_by(Event.event_date.desc())
        .limit(RESULTS_PER_TYPE)
        .all()
    )
    results += [
        SearchResultItem(
            type="event", id=e.id,
            title=e.title,
            subtitle=e.event_date.strftime("%d/%m/%Y"),
            href="/evenements",
        )
        for e in events
    ]

    collectes = (
        db.query(Collecte)
        .filter(or_(
            func.lower(Collecte.title).like(term),
            func.lower(Collecte.beneficiary_name).like(term),
        ))
        .order_by(Collecte.created_at.desc())
        .limit(RESULTS_PER_TYPE)
        .all()
    )
    results += [
        SearchResultItem(
            type="collecte", id=c.id,
            title=c.title,
            subtitle=c.beneficiary_name,
            href=f"/collectes/{c.id}",
        )
        for c in collectes
    ]

    return results
