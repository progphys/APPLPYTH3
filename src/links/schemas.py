from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from uuid import UUID

class LinkCreateRequest(BaseModel):
    long_link: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None 

class LinkNewCreateRequest(BaseModel):
    new_long_link: str

class LinkResponse(BaseModel):
    id: int
    long_link: str
    short_link: str
    auth: bool
    user_id: Optional[UUID] 
    start_date: datetime
    last_date: datetime
    num: int
    expires_at: Optional[datetime]


class LinkStats(BaseModel):
    long_link: str
    created_at: datetime
    clicks_count: int
    last_used: datetime