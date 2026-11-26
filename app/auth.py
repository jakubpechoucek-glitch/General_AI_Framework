"""Local authentication (email + password) and permission helpers.

For production in an M365 organisation, replace the login with Microsoft Entra ID
(OIDC) and map the signed-in email to the User record; the rest of the app only
relies on `current_user`.
"""
import hashlib
import hmac
import secrets

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Assessment, User

_ITER = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER)
    return f"pbkdf2_sha256${_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(dk.hex(), digest)


def temp_password() -> str:
    return secrets.token_urlsafe(9)


class LoginRequired(Exception):
    pass


class Forbidden(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        request.session.pop("uid", None)
        raise LoginRequired()
    if user.must_change_password and request.url.path not in ("/password", "/logout"):
        raise LoginRequired("password")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise Forbidden()
    return user


def is_manager(db: Session, user: User) -> bool:
    return db.query(User.id).filter(User.manager_id == user.id).first() is not None


def reporting_scope(db: Session, user: User):
    """Users whose results this user may see in reports (excluding self)."""
    q = db.query(User).filter(User.active.is_(True))
    if user.is_admin:
        return q
    if user.is_calibrator and user.team_id:
        return q.filter(User.team_id == user.team_id)
    return q.filter(User.manager_id == user.id)


def can_view(user: User, a: Assessment) -> bool:
    return (user.is_admin or a.employee_id == user.id or a.manager_id == user.id
            or a.employee.manager_id == user.id
            or (user.is_calibrator and user.team_id and a.employee.team_id == user.team_id))


def can_review(user: User, a: Assessment) -> bool:
    """Manager review (R07/R08): the employee's manager, or an admin."""
    return user.is_admin or (a.employee_id != user.id and
                             (a.manager_id == user.id or a.employee.manager_id == user.id))


def can_calibrate(user: User, a: Assessment) -> bool:
    """Validated level & finalisation (R09): manager, calibration owner of the team, admin."""
    if a.employee_id == user.id and not user.is_admin:
        return False
    return can_review(user, a) or bool(
        user.is_calibrator and user.team_id and a.employee.team_id == user.team_id)
