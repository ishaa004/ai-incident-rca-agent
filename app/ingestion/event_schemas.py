from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LogEventIn(BaseModel):
    type: Literal["log"] = "log"
    incident_id: str
    service: str
    level: str
    message: str
    timestamp: datetime
    raw: dict = {}


class MetricEventIn(BaseModel):
    type: Literal["metric"] = "metric"
    incident_id: str
    service: str
    metric_name: str
    value: float
    unit: str = ""
    timestamp: datetime


class TraceEventIn(BaseModel):
    type: Literal["trace"] = "trace"
    incident_id: str
    trace_id: str
    span_id: str
    parent_span_id: str = ""
    service: str
    operation: str
    duration_ms: float
    status: str
    timestamp: datetime


class DeploymentEventIn(BaseModel):
    type: Literal["deployment"] = "deployment"
    incident_id: str
    service: str
    version: str
    description: str = ""
    timestamp: datetime


IncidentEvent = LogEventIn | MetricEventIn | TraceEventIn | DeploymentEventIn
