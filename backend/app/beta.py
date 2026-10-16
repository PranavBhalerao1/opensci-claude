"""Access and credits: private-beta approval, per-user USD caps and paid plans.

Two ways in. Beta access lives in beta_users and is managed from /admin (approved;
cap_usd in USD, NULL = unlimited, which is how the team runs). A paid plan lives in
subscriptions, written by the website's Stripe webhook: it grants access and
credits_usd of compute per billing period, so the allowance renews each period.
A user's spend is the cost OpenScientist already tracks for them: model calls
(usage) plus cloud GPU jobs (gpu_usage). E2B sandbox time is not metered.

Everything reads the database on each check, so approving a user or raising a cap
takes effect on their next request without a token refresh.
"""

import math
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from sqlmodel import Session, func, select

from .auth import CurrentUser, get_current_user
from .db import BetaUser, GpuUsage, Project, Subscription, Usage, engine

PENDING_MESSAGE = (
    "OpenScientist is currently in private beta. Your account has been created and is awaiting beta approval."
)
LIMIT_MESSAGE = (
    "Out of credits. You've used this period's credits. "
    "Upgrade your plan on the Pricing page, or wait for your credits to renew."
)

PAID_STATUSES = {"active", "trialing"}
# A renewal's webhook can land a little after the period it replaces has ended.
RENEWAL_GRACE = timedelta(days=2)

# Execution pause reason; the UI keys on the "beta_limit_reached" prefix.
LIMIT_PAUSE = "beta_limit_reached: beta usage limit reached"


class BetaLimitReached(Exception):
    def __init__(self) -> None:
        super().__init__(LIMIT_MESSAGE)


def get_beta_user(user_id: str) -> BetaUser | None:
    with Session(engine) as s:
        return s.get(BetaUser, user_id)


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)  # SQLite drops the zone


def get_plan(user_id: str) -> Subscription | None:
    """The user's paid plan while it is in good standing, else None."""
    with Session(engine) as s:
        sub = s.get(Subscription, user_id)
    if not sub or sub.status not in PAID_STATUSES:
        return None
    if sub.period_end and _utc(sub.period_end) + RENEWAL_GRACE < datetime.now(timezone.utc):
        return None
    return sub


def get_user_spend(user_id: str, since: datetime | None = None) -> float:
    """USD spent by the user, in total or since `since` (a plan's current period)."""
    with Session(engine) as s:
        llm = select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.user_id == user_id)
        gpu = select(func.coalesce(func.sum(GpuUsage.cost), 0.0)).where(GpuUsage.user_id == user_id)
        if since is not None:
            llm, gpu = llm.where(Usage.created_at >= since), gpu.where(GpuUsage.created_at >= since)
        return float(s.exec(llm).one()) + float(s.exec(gpu).one())


def _allowance(user_id: str) -> tuple[bool, float | None, float, Subscription | None]:
    """(has access, allowance in USD or None for unlimited, spend counted against it, plan).

    An uncapped beta account (the team) stays unlimited; otherwise a paid plan's
    per-period credits replace any beta cap; otherwise the beta cap applies."""
    beta = get_beta_user(user_id)
    plan = get_plan(user_id)
    approved = bool(beta and beta.approved)
    if approved and beta.cap_usd is None:
        return True, None, get_user_spend(user_id), plan
    if plan:
        return True, plan.credits_usd, get_user_spend(user_id, _utc(plan.period_start) if plan.period_start else None), plan
    return approved, beta.cap_usd if beta else None, get_user_spend(user_id), None


def has_access(user_id: str) -> bool:
    beta = get_beta_user(user_id)
    return bool(beta and beta.approved) or get_plan(user_id) is not None


def get_user_remaining(user_id: str) -> float:
    """USD the user may still spend: inf when unlimited, 0 without access."""
    access, allowance, spent, _ = _allowance(user_id)
    if not access:
        return 0.0
    if allowance is None:
        return math.inf
    return max(0.0, allowance - spent)


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
    access, allowance, spent, plan = _allowance(user_id)
    return {
        "beta_approved": access,
        "unlimited": access and allowance is None,
        "cap_usd": allowance,  # this period's allowance when on a plan
        "spent_usd": round(spent, 4),
        "remaining_usd": None if allowance is None else round(max(0.0, allowance - spent), 4),
        "plan": plan.plan if plan else None,
        "period_end": _utc(plan.period_end).isoformat() if plan and plan.period_end else None,
    }


def require_approved(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not has_access(user.id):
        raise HTTPException(403, {"code": "beta_pending", "message": PENDING_MESSAGE})
    return user


def require_allowance(user: CurrentUser = Depends(require_approved)) -> CurrentUser:
    """For routes that start billable work: approved and spend still under the cap."""
    if get_user_remaining(user.id) <= 0:
        raise HTTPException(403, {"code": "beta_limit_reached", "message": LIMIT_MESSAGE})
    return user
