from sqlmodel import Session, col, select

from ..models import EvaluationRun


def list_evaluation_runs(
    session: Session, organization_id: str = "local"
) -> list[EvaluationRun]:
    return list(session.exec(
        select(EvaluationRun)
        .where(EvaluationRun.organization_id == organization_id)
        .order_by(col(EvaluationRun.created_at).desc())
    ).all())
