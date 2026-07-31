from pydantic import BaseModel


class AdminPendingCounts(BaseModel):
    beneficiaries: int = 0
    death_reports: int = 0
    cotisations: int = 0
    collectes: int = 0
