"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    expires_at: datetime
    start_date: Optional[datetime] = None


def serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "message": doc["message"],
        "start_date": doc.get("start_date").isoformat() if doc.get("start_date") else None,
        "expires_at": doc["expires_at"].isoformat(),
        "created_at": doc["created_at"].isoformat(),
        "updated_at": doc["updated_at"].isoformat(),
        "created_by": doc["created_by"]
    }


def ensure_authenticated_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def validate_dates(payload: AnnouncementPayload) -> None:
    if payload.start_date and payload.expires_at <= payload.start_date:
        raise HTTPException(
            status_code=400,
            detail="Expiration date must be later than the start date"
        )


def parse_announcement_id(announcement_id: str) -> ObjectId:
    try:
        return ObjectId(announcement_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements for public display"""
    now = datetime.utcnow()

    query = {
        "expires_at": {"$gt": now},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": now}}
        ]
    }

    docs = announcements_collection.find(query).sort("created_at", -1)
    return [serialize_announcement(doc) for doc in docs]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements_for_management(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management view (authenticated users only)"""
    ensure_authenticated_teacher(teacher_username)

    docs = announcements_collection.find({}).sort("created_at", -1)
    return [serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create a new announcement (authenticated users only)"""
    teacher = ensure_authenticated_teacher(teacher_username)
    validate_dates(payload)

    now = datetime.utcnow()
    new_doc = {
        "message": payload.message.strip(),
        "start_date": payload.start_date,
        "expires_at": payload.expires_at,
        "created_at": now,
        "updated_at": now,
        "created_by": teacher["username"]
    }

    if not new_doc["message"]:
        raise HTTPException(status_code=400, detail="Announcement message cannot be empty")

    result = announcements_collection.insert_one(new_doc)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an announcement (authenticated users only)"""
    ensure_authenticated_teacher(teacher_username)
    validate_dates(payload)
    object_id = parse_announcement_id(announcement_id)

    update_result = announcements_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "message": payload.message.strip(),
                "start_date": payload.start_date,
                "expires_at": payload.expires_at,
                "updated_at": datetime.utcnow()
            }
        }
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to fetch updated announcement")

    return serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement (authenticated users only)"""
    ensure_authenticated_teacher(teacher_username)
    object_id = parse_announcement_id(announcement_id)

    delete_result = announcements_collection.delete_one({"_id": object_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
