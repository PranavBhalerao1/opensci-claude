"""Private beta: access approval and a per-user USD spending cap.

Approval and caps live in the beta_users table and are managed by hand in the
Supabase table editor (approved false → true; cap_usd in USD, NULL = unlimited).
A user's spend is the cost OpenScientist already tracks for them: model calls
(usage) plus cloud GPU jobs (gpu_usage). E2B sandbox time is not metered.

Everything reads the database on each check, so approving a user or raising a cap
takes effect on their next request without a token refresh.
"""

import math

from fastapi import Depends, HTTPException
from sqlmodel import Session, func, select

from .auth import CurrentUser, get_current_user
from .db import BetaUser, GpuUsage, Project, Usage, engine

PENDING_MESSAGE = (
    "OpenScientist is currently in private beta. Your account has been created and is awaiting beta approval."
)
LIMIT_MESSAGE = (
    "Beta usage limit reached. You've used your current beta allowance. "
    "Contact the OpenScientist team if you need additional access."
)
# Execution pause reason; the UI keys on the "beta_limit_reached" prefix.
LIMIT_PAUSE = "beta_limit_reached: beta usage limit reached"


class BetaLimitReached(Exception):
    def __init__(self) -> None:
        super().__init__(LIMIT_MESSAGE)


def get_beta_user(user_id: str) -> BetaUser | None:
    with Session(engine) as s:
        return s.get(BetaUser, user_id)


def get_user_spend(user_id: str) -> float:
    with Session(engine) as s:
        llm = s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.user_id == user_id)).one()
        gpu = s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0)).where(GpuUsage.user_id == user_id)).one()
    return float(llm) + float(gpu)


def get_user_remaining(user_id: str) -> float:
    """USD the user may still spend: inf when uncapped, 0 when not approved (or no row)."""
    beta = get_beta_user(user_id)
    if not beta or not beta.approved:
        return 0.0
    if beta.cap_usd is None:
        return math.inf
    return max(0.0, beta.cap_usd - get_user_spend(user_id))


def owner_of(project_id: str | None) -> str | None:
    if not project_id:
        return None
    with Session(engine) as s:
        return s.exec(select(Project.user_id).where(Project.id == project_id)).first()


def project_allowance(project_id: str) -> float:
    """Remaining beta allowance of the project's owner. Unlimited for a project with no
    owner, which only the offline test suite creates (Postgres requires one)."""
    owner = owner_of(project_id)
    return math.inf if owner is None else get_user_remaining(owner)


def check_project_allowance(project_id: str) -> None:
    if project_allowance(project_id) <= 0:
        raise BetaLimitReached()


def status(user_id: str) -> dict:
    beta = get_beta_user(user_id)
    approved = bool(beta and beta.approved)
    cap = beta.cap_usd if beta else None
    spent = get_user_spend(user_id)
    return {
        "beta_approved": approved,
        "unlimited": approved and cap is None,
        "cap_usd": cap,
        "spent_usd": round(spent, 4),
        "remaining_usd": None if cap is None else round(max(0.0, cap - spent), 4),
    }


def require_approved(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    beta = get_beta_user(user.id)
    if not beta or not beta.approved:
        raise HTTPException(403, {"code": "beta_pending", "message": PENDING_MESSAGE})
    return user


def require_allowance(user: CurrentUser = Depends(require_approved)) -> CurrentUser:
    """For routes that start billable work: approved and spend still under the cap."""
    if get_user_remaining(user.id) <= 0:
        raise HTTPException(403, {"code": "beta_limit_reached", "message": LIMIT_MESSAGE})
    return user
