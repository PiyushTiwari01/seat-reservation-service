from fastapi import Header, HTTPException


def get_current_user(
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = authorization[len("Bearer "):].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token
