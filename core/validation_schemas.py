"""Validation 阶段使用的独立数据结构。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ValidationFinding:
    """一条需要用户关注的校验发现。"""

    finding_id: str
    scope: str
    row_index: int | None
    column_name: str | None
    observed_value: Any
    issue_type: str
    reason: str
    suggested_value: Any = None
    confidence: str = "low"
    severity: str = "medium"
    location_status: str = "unvalidated"


@dataclass
class ValidationRunLog:
    """一次 Validation 调用的安全运行记录。"""

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str | None = None
    provider: str = ""
    model: str = ""
    elapsed_seconds: float = 0.0
    success: bool = False
    error_category: str | None = None
    error_message: str | None = None
    raw_response: str = ""


@dataclass
class ValidationResult:
    """Validation 的独立输出，不会覆盖 ExperimentResult。"""

    warnings: list[str] = field(default_factory=list)
    suggestions: list[ValidationFinding] = field(default_factory=list)
    uncertain_items: list[ValidationFinding] = field(default_factory=list)
    provider: str = ""
    status: str = "completed"
    response_metadata: dict[str, Any] = field(default_factory=dict)
    run_log: ValidationRunLog | None = None
