"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    expiration_date: str = Field(min_length=10, max_length=10)
    start_date: Optional[str] = Field(default=None, min_length=10, max_length=10)


def _validate_iso_date(date_text: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be in YYYY-MM-DD format"
        ) from exc


def _ensure_teacher(username: Optional[str]) -> Dict[str, Any]:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(raw["_id"]),
        "title": raw["title"],
        "message": raw["message"],
        "start_date": raw.get("start_date"),
        "expiration_date": raw["expiration_date"],
        "created_by": raw.get("created_by", "")
    }


def _validate_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot be empty")
    return cleaned


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements active for today's date."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": ""},
            {"start_date": {"$lte": today}}
        ]
    }

    announcements = announcements_collection.find(query).sort(
        [("expiration_date", 1), ("title", 1)]
    )
    return [_serialize_announcement(doc) for doc in announcements]


@router.get("", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return all announcements for authenticated users."""
    _ensure_teacher(teacher_username)

    announcements = announcements_collection.find({}).sort(
        [("expiration_date", 1), ("title", 1)]
    )
    return [_serialize_announcement(doc) for doc in announcements]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementUpsert,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement."""
    teacher = _ensure_teacher(teacher_username)

    expiration_dt = _validate_iso_date(payload.expiration_date, "expiration_date")
    start_dt = None

    if payload.start_date:
        start_dt = _validate_iso_date(payload.start_date, "start_date")

    if start_dt and start_dt > expiration_dt:
        raise HTTPException(status_code=400, detail="start_date must be on or before expiration_date")

    title = _validate_required_text(payload.title, "title")
    message = _validate_required_text(payload.message, "message")
    normalized_start_date = payload.start_date or None

    doc = {
        "title": title,
        "message": message,
        "start_date": normalized_start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher["username"]
    }
    insert_result = announcements_collection.insert_one(doc)
    created = announcements_collection.find_one({"_id": insert_result.inserted_id})

    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpsert,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _ensure_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    expiration_dt = _validate_iso_date(payload.expiration_date, "expiration_date")
    start_dt = None

    if payload.start_date:
        start_dt = _validate_iso_date(payload.start_date, "start_date")

    if start_dt and start_dt > expiration_dt:
        raise HTTPException(status_code=400, detail="start_date must be on or before expiration_date")

    title = _validate_required_text(payload.title, "title")
    message = _validate_required_text(payload.message, "message")
    normalized_start_date = payload.start_date or None

    update_result = announcements_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "title": title,
                "message": message,
                "start_date": normalized_start_date,
                "expiration_date": payload.expiration_date
            }
        }
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement."""
    _ensure_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    delete_result = announcements_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
