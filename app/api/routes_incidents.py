from fastapi import APIRouter, HTTPException

from app.agents.orchestrator import investigate, try_parse_json
from app.api.schemas import InvestigateRequest, InvestigateResponse, InvestigationStatusResponse
from app.cache import get_investigation_state
from app.db import Investigation, get_session

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate_incident(req: InvestigateRequest) -> InvestigateResponse:
    result = await investigate(req.incident_id, req.summary)

    report = try_parse_json(result.verified_report) or result.verified_report

    session = get_session()
    try:
        record = Investigation(
            incident_id=req.incident_id,
            summary=req.summary,
            status="complete",
            root_cause=report.get("root_cause", "") if isinstance(report, dict) else "",
            report_json=report if isinstance(report, dict) else {"raw": report},
        )
        session.add(record)
        session.commit()
    finally:
        session.close()

    return InvestigateResponse(
        incident_id=req.incident_id,
        status="complete",
        report=report,
        specialist_findings={r.name: r.findings for r in result.specialist_findings},
    )


@router.get("/{incident_id}/status", response_model=InvestigationStatusResponse)
def get_status(incident_id: str) -> InvestigationStatusResponse:
    state = get_investigation_state(incident_id)
    return InvestigationStatusResponse(incident_id=incident_id, state=state)


@router.get("/{incident_id}")
def get_investigation(incident_id: str):
    session = get_session()
    try:
        record = (
            session.query(Investigation)
            .filter(Investigation.incident_id == incident_id)
            .order_by(Investigation.created_at.desc())
            .first()
        )
        if not record:
            raise HTTPException(status_code=404, detail="No investigation found for this incident_id")
        return {
            "incident_id": record.incident_id,
            "summary": record.summary,
            "status": record.status,
            "root_cause": record.root_cause,
            "report": record.report_json,
            "created_at": record.created_at.isoformat(),
        }
    finally:
        session.close()
