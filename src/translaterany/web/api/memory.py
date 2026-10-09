"""Endpoints RESTful para edição e persistência de memórias da série."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from translaterany.memory.models import CharacterEntry, GlossaryEntry, StoryMemory
from translaterany.web.services.memory_service import MemoryDoc, MemoryService

router = APIRouter(prefix="/series/{key}/memory", tags=["memory"])


def get_memory_service(request: Request) -> MemoryService:
    return request.app.state.memory_service


@router.get("", response_model=MemoryDoc)
def get_memory(key: str, request: Request) -> MemoryDoc:
    svc = get_memory_service(request)
    return svc.load_memory(key)


@router.post("/characters", response_model=dict[str, str])
def add_character(key: str, character: CharacterEntry, request: Request) -> dict[str, str]:
    svc = get_memory_service(request)
    svc.add_character(key, character)
    return {"message": "Personagem salvo com sucesso", "name": character.name}


@router.delete("/characters/{name}", response_model=dict[str, str])
def delete_character(key: str, name: str, request: Request) -> dict[str, str]:
    svc = get_memory_service(request)
    deleted = svc.delete_character(key, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")
    return {"message": "Personagem removido com sucesso", "name": name}


@router.post("/glossary", response_model=dict[str, str])
def add_glossary_term(key: str, entry: GlossaryEntry, request: Request) -> dict[str, str]:
    svc = get_memory_service(request)
    svc.add_glossary_term(key, entry)
    return {"message": "Termo do glossário salvo com sucesso", "term": entry.term}


@router.delete("/glossary/{term}", response_model=dict[str, str])
def delete_glossary_term(key: str, term: str, request: Request) -> dict[str, str]:
    svc = get_memory_service(request)
    deleted = svc.delete_glossary_term(key, term)
    if not deleted:
        raise HTTPException(status_code=404, detail="Termo não encontrado")
    return {"message": "Termo removido com sucesso", "term": term}


@router.put("/story", response_model=dict[str, str])
def update_story(key: str, story: StoryMemory, request: Request) -> dict[str, str]:
    svc = get_memory_service(request)
    svc.save_story(key, story)
    return {"message": "História atualizada com sucesso"}
