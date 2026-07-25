from uuid import UUID


def generate_reference_code(first_name: str, last_name: str,
                             collecte_id: UUID, contribution_id: UUID) -> str:
    """
    Code court à coller dans la note du virement Wero, ex: 'JD-3F2A-9B1C'.
    Dérivé déterministiquement des UUID existants (pas de génération
    aléatoire, pas de vérification d'unicité en base) : le trésorier
    l'utilise comme indice de recherche, pas comme clé stricte — le
    rapprochement final se fait aussi via montant + date.
    """
    initials = (first_name[:1] + last_name[:1]).upper()
    collecte_short = str(collecte_id).replace("-", "")[:4].upper()
    contrib_short = str(contribution_id).replace("-", "")[:4].upper()
    return f"{initials}-{collecte_short}-{contrib_short}"
