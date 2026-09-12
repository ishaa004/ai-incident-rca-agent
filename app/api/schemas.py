from pydantic import BaseModel


class InvestigateRequest(BaseModel):
    incident_id: str
    summary: str


class InvestigateResponse(BaseModel):
    incident_id: str
    status: str
    report: dict | str
    specialist_findings: dict[str, str]


class InvestigationStatusResponse(BaseModel):
    incident_id: str
    state: dict | None
