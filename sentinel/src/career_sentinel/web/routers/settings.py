"""settings / preferences 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ... import store
from ...models import JobPreferences, Settings
from ..deps import get_db_path

router = APIRouter()


@router.get("/api/settings")
def get_settings(db_path: str = Depends(get_db_path)) -> dict:
    return store.load_settings(store.connect(db_path)).model_dump()


@router.put("/api/settings")
def put_settings(settings: Settings, db_path: str = Depends(get_db_path)) -> dict:
    store.save_settings(store.connect(db_path), settings)
    return settings.model_dump()


@router.get("/api/preferences")
def get_preferences(db_path: str = Depends(get_db_path)) -> dict:
    return store.load_preferences(store.connect(db_path)).model_dump()


@router.put("/api/preferences")
def put_preferences(prefs: JobPreferences, db_path: str = Depends(get_db_path)) -> dict:
    store.save_preferences(store.connect(db_path), prefs)
    return prefs.model_dump()
