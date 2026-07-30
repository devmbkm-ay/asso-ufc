from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from models import MemberNotification, MemberRole, Role, RoleName

# Rôles habilités à instruire les signalements/désignations — mêmes rôles
# que RequirePresidentOrAdmin (cf. app/core/deps.py), dupliqués ici pour
# éviter une dépendance circulaire vers deps.py.
ADMIN_ROLES = (RoleName.super_admin, RoleName.president)


def notify_member(db: Session, member_id: UUID, type: str, message: str, link: str | None = None) -> None:
    """
    Dépose une notification in-app pour un membre — ne commit pas elle-même,
    s'insère dans la transaction déjà ouverte par l'appelant (même convention
    que _save_notification dans app/api/v1/routes/notifications.py).
    """
    db.add(MemberNotification(
        id=uuid4(),
        member_id=member_id,
        type=type,
        message=message,
        link=link,
    ))


def notify_admins(db: Session, type: str, message: str, link: str | None = None) -> None:
    """
    Dépose la même notification pour chaque membre habilité à instruire
    (super_admin, président) — utilisé quand un nouvel élément arrive dans
    une file d'attente admin (signalement, désignation) plutôt que quand le
    statut d'un élément existant change pour son auteur.
    """
    admin_ids = (
        db.query(MemberRole.member_id)
        .join(Role, Role.id == MemberRole.role_id)
        .filter(Role.name.in_(ADMIN_ROLES))
        .distinct()
        .all()
    )
    for (member_id,) in admin_ids:
        notify_member(db, member_id, type, message, link)
