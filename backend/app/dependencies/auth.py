import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserRole
from app.utils.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not cred:
        raise HTTPException(401, "Not authenticated")
    try:
        uid = int(decode_token(cred.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(401, "Account not available")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Admin access required")
    return user


def get_current_user_optional(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Same as get_current_user but allows anonymous callers.

    Used by endpoints that are public yet gain capabilities (e.g. reading your
    own orders) once a valid token is supplied. An invalid token is ignored
    rather than rejected, so the public path keeps working.
    """
    if not cred:
        return None
    try:
        uid = int(decode_token(cred.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    user = db.get(User, uid)
    return user if user and user.is_active else None
