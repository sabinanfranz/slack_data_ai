from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import UserCache


def upsert_user_cache(db: Session, user_obj: dict) -> None:
    """
    Store or update a user's display/real name in users_cache.
    """
    user_id = user_obj.get("id")
    if not user_id:
        return

    profile = user_obj.get("profile") or {}
    display_name = (profile.get("display_name") or "").strip()
    real_name = (profile.get("real_name") or "").strip()
    name_fallback = (user_obj.get("name") or "").strip()

    best_name = display_name or real_name or name_fallback or None

    row = db.get(UserCache, user_id)
    if row:
        row.display_name = best_name
        row.real_name = real_name or best_name
    else:
        row = UserCache(
            user_id=user_id,
            display_name=best_name,
            real_name=real_name or best_name,
        )
        db.add(row)
