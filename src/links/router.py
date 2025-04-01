from fastapi import APIRouter, Depends, HTTPException, status, Request

from fastapi.responses import RedirectResponse
from sqlalchemy import select, insert, update,delete
from sqlalchemy.ext.asyncio import AsyncSession
import time
from database import get_async_session
from .models import links
from .schemas import LinkResponse, LinkCreateRequest,LinkStats,LinkNewCreateRequest
import hashlib
from datetime import datetime 
from auth.users import current_active_user  
from auth.db import User  
from typing import Optional, List
from auth.users import fastapi_users 
from fastapi_cache.decorator import cache
from tasks.tasks import delete_expired_link
from fastapi_cache import FastAPICache
router = APIRouter(
    prefix="/links",
    tags=["links"]
)
def generate_short_link(long_link: str) -> str:
    return hashlib.md5(long_link.encode()).hexdigest()[:8]

optional_current_user = fastapi_users.current_user(optional=True)

@router.post("/shorten", response_model=LinkResponse)
async def shorten_link(
    link_req: LinkCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: Optional[User] = Depends(optional_current_user)
):
    if current_user:
        stmt = select(links).where(
            (links.c.long_link == link_req.long_link) &
            (links.c.user_id == current_user.id)
        )
    else:
        stmt = select(links).where(links.c.long_link == link_req.long_link)
    result = await session.execute(stmt)
    existing_link = result.scalar_one_or_none()
    if existing_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка уже существует."
        )

    if link_req.custom_alias:
        stmt = select(links).where(links.c.short_link == link_req.custom_alias)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Custom alias уже используется. Пожалуйста, выберите другой."
            )
        short_link = link_req.custom_alias
    else:
        short_link = generate_short_link(link_req.long_link)
        stmt = select(links).where(links.c.short_link == short_link)
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка генерации уникального alias. Попробуйте снова."
            )

    link_data = {
        "long_link": link_req.long_link,
        "short_link": short_link,
        "auth": True if current_user else False,
        "user_id": current_user.id if current_user else None,  
        "start_date": datetime.utcnow(),
        "last_date": datetime.utcnow(),
        "num": 0,
        "expires_at": link_req.expires_at  
    }

    statement = insert(links).values(**link_data).returning(links.c.id)
    result = await session.execute(statement)
    await session.commit()

    new_id = result.scalar_one()
    
    if link_req.expires_at:
        delete_expired_link.apply_async(
    args=[new_id],
    eta=link_req.expires_at,
    queue='celery' 
)
    
    stmt = select(links).where(links.c.id == new_id)
    query_result = await session.execute(stmt)
    new_link = query_result.fetchone()

    return new_link


def short_link_key_builder(function, *args, **kwargs) -> str:
    short_link = args[0]
    return f"long_link:{short_link}"

@cache(expire=60, key_builder=short_link_key_builder)
async def get_cached_long_link(short_link: str, session: AsyncSession) -> str:
    stmt = select(links.c.long_link).where(links.c.short_link == short_link)
    result = await session.execute(stmt)
    long_link = result.scalar()
    if not long_link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    return long_link

@router.get("/")
async def get_long_link(
    short_link: str,
    session: AsyncSession = Depends(get_async_session)
):
    long_link = await get_cached_long_link(short_link, session)
    
    if not long_link.startswith(("http://", "https://")):
        long_link = "http://" + long_link

    stmt = update(links).where(links.c.short_link == short_link).values(num=links.c.num + 1)
    await session.execute(stmt)
    await session.commit()
    
    return RedirectResponse(url=long_link)



@router.get("/{short_code}/stats", response_model=LinkStats)
@cache(expire=60) 
async def get_link_stats(
    short_code: str,
    session: AsyncSession = Depends(get_async_session)
):
    stmt = select(
        links.c.long_link,
        links.c.start_date,
        links.c.num,
        links.c.last_date
    ).where(links.c.short_link == short_code)

    result = await session.execute(stmt)
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )
    return LinkStats(
        long_link=row.long_link,
        created_at=row.start_date,
        clicks_count=row.num,
        last_used=row.last_date
    )

@router.get("/search")
@cache(expire=30)
async def search_short_link(
    long_link: str,
    session: AsyncSession = Depends(get_async_session)
):
    stmt = select(links.c.short_link).where(links.c.long_link == long_link)
    result = await session.execute(stmt)
    short_link = result.scalar()

    if not short_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена."
        )
    return short_link

@router.delete("/{short_code}")
async def delete_link(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
):
    stmt = select(links).where(
        (links.c.short_link == short_code) &
        (links.c.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    link_record = result.scalar_one_or_none()

    if not link_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена или доступ запрещён."
        )

    delete_stmt = delete(links).where(links.c.short_link == short_code)
    await session.execute(delete_stmt)
    await session.commit()
    cache_key = f"long_link:{short_code}"
    backend = FastAPICache.get_backend()
    await backend.clear(cache_key)
    return {"detail": "Ссылка успешно удалена."}

@router.put("/{short_code}", response_model=LinkResponse)
async def update_link(
    short_code: str,
    link_update: LinkNewCreateRequest, 
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
):

    stmt = select(links).where(
        (links.c.short_link == short_code) &
        (links.c.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    link_record = result.scalar_one_or_none()
    if not link_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена или доступ запрещён."
        )

    update_stmt = (
        update(links)
        .where(links.c.short_link == short_code)
        .values(
            long_link=link_update.new_long_link,
            last_date=datetime.utcnow()
        )
        .returning(links)
    )
    result = await session.execute(update_stmt)
    await session.commit()
    
    updated_link = result.mappings().all()
    if updated_link:
        updated_link = dict(updated_link[0]) 
    
    cache_key = f"long_link:{short_code}"
    backend = FastAPICache.get_backend()
    await backend.clear(cache_key)
    return updated_link

@router.get("/expired", response_model=List[LinkResponse])
@cache(expire=60)
async def get_expired_links(
    session: AsyncSession = Depends(get_async_session)
):
    now = datetime.utcnow()
    stmt = select(links).where(
        links.c.expires_at != None,
        links.c.expires_at < now
    )
    result = await session.execute(stmt)
    expired_links = result.mappings().all()
    return expired_links

