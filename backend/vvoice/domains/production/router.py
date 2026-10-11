from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from starlette.background import BackgroundTask

from vvoice.domains.production import schemas as s
from vvoice.domains.production.service import ProductionError
from vvoice.shared.security.auth import Principal, require_scope


class ProductionRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                return await original(request)
            except ProductionError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return handle


router = APIRouter(route_class=ProductionRoute)
read = require_scope("production:read")
write = require_scope("production:write")
review = require_scope("production:review")


@router.post("/projects", response_model=s.ProjectResponse, status_code=201)
def create_project(request: Request, body: s.ProjectCreate, actor: Principal = Depends(write)):
    return request.app.state.container.production.create_project(body.model_dump(), actor)


@router.get("/projects", response_model=s.Page[s.ProjectResponse])
def list_projects(request: Request, limit: int = Query(100, ge=1, le=200),
                  offset: int = Query(0, ge=0), actor: Principal = Depends(read)):
    return request.app.state.container.production.list_projects(actor, limit=limit, offset=offset)


@router.get("/projects/{project_id}", response_model=s.ProjectResponse)
def get_project(project_id: str, request: Request, actor: Principal = Depends(read)):
    return request.app.state.container.production.get_project(project_id, actor)


@router.patch("/projects/{project_id}", response_model=s.ProjectResponse)
def update_project(project_id: str, request: Request, body: s.ProjectPatch,
                   actor: Principal = Depends(write)):
    return request.app.state.container.production.update_project(
        project_id, body.model_dump(exclude_unset=True), actor,
    )


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, request: Request, actor: Principal = Depends(read)):
    project = request.app.state.container.production.get_project(project_id, actor)
    return {"owner_id": project["owner_id"], "revision": project["revision"],
            "members": project["members"]}


@router.put("/projects/{project_id}/members", response_model=s.ProjectResponse)
def update_members(project_id: str, request: Request, body: s.MembersUpdate,
                   actor: Principal = Depends(write)):
    return request.app.state.container.production.update_members(project_id, body.model_dump(), actor)


@router.get("/projects/{project_id}/segments", response_model=s.Page[s.SegmentResponse])
def list_segments(project_id: str, request: Request, limit: int = Query(100, ge=1, le=200),
                  offset: int = Query(0, ge=0), actor: Principal = Depends(read)):
    return request.app.state.container.production.list_segments(
        project_id, actor, limit=limit, offset=offset,
    )


@router.post("/projects/{project_id}/segments", response_model=s.SegmentResponse, status_code=201)
def create_segment(project_id: str, request: Request, body: s.SegmentCreate,
                   actor: Principal = Depends(write)):
    return request.app.state.container.production.create_segment(project_id, body.model_dump(), actor)


@router.get("/projects/{project_id}/segments/{segment_id}", response_model=s.SegmentResponse)
def get_segment(project_id: str, segment_id: str, request: Request, actor: Principal = Depends(read)):
    return request.app.state.container.production.get_segment(project_id, segment_id, actor)


@router.patch("/projects/{project_id}/segments/{segment_id}", response_model=s.SegmentResponse)
def update_segment(project_id: str, segment_id: str, request: Request, body: s.SegmentPatch,
                   actor: Principal = Depends(write)):
    return request.app.state.container.production.update_segment(
        project_id, segment_id, body.model_dump(exclude_unset=True), actor,
    )


@router.get("/projects/{project_id}/segments/{segment_id}/revisions")
def segment_revisions(project_id: str, segment_id: str, request: Request,
                      actor: Principal = Depends(read)):
    return request.app.state.container.production.segment_revisions(project_id, segment_id, actor)


@router.post("/projects/{project_id}/segments/{segment_id}/takes",
             response_model=s.TakeResponse, status_code=202)
def create_take(project_id: str, segment_id: str, request: Request, body: s.TakeCreate,
                idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                actor: Principal = Depends(write)):
    return request.app.state.container.production.create_take(
        project_id, segment_id, body.model_dump(exclude_unset=True), actor,
        idempotency_key=idempotency_key,
    )


@router.get("/projects/{project_id}/segments/{segment_id}/takes", response_model=s.Page[s.TakeResponse])
def list_takes(project_id: str, segment_id: str, request: Request,
               limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
               actor: Principal = Depends(read)):
    return request.app.state.container.production.list_takes(
        project_id, segment_id, actor, limit=limit, offset=offset,
    )


@router.patch("/projects/{project_id}/takes/{take_id}/review", response_model=s.TakeResponse)
def review_take(project_id: str, take_id: str, request: Request, body: s.TakeReview,
                actor: Principal = Depends(review)):
    return request.app.state.container.production.review_take(
        project_id, take_id, body.model_dump(), actor,
    )


@router.put("/projects/{project_id}/segments/{segment_id}/selection", response_model=s.SegmentResponse)
def select_take(project_id: str, segment_id: str, request: Request, body: s.TakeSelection,
                actor: Principal = Depends(review)):
    return request.app.state.container.production.select_take(
        project_id, segment_id, body.model_dump(), actor,
    )


@router.get("/projects/{project_id}/takes/{take_id}/audio", response_class=FileResponse,
            responses={200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}})
def take_audio(project_id: str, take_id: str, request: Request, actor: Principal = Depends(read)):
    path = request.app.state.container.production.take_audio(project_id, take_id, actor)
    return FileResponse(path, media_type="audio/wav", filename=f"{take_id}.wav")


@router.get("/projects/{project_id}/dictionary", response_model=s.DictionaryResponse)
def get_dictionary(project_id: str, request: Request, actor: Principal = Depends(read)):
    return request.app.state.container.production.dictionary(project_id, actor)


@router.put("/projects/{project_id}/dictionary", response_model=s.DictionaryResponse)
def update_dictionary(project_id: str, request: Request, body: s.DictionaryUpdate,
                      actor: Principal = Depends(write)):
    return request.app.state.container.production.update_dictionary(project_id, body.model_dump(), actor)


@router.get("/projects/{project_id}/dictionary/revisions")
def dictionary_revisions(project_id: str, request: Request, actor: Principal = Depends(read)):
    return request.app.state.container.production.dictionary_revisions(project_id, actor)


@router.post("/projects/{project_id}/dictionary/preview")
def preview_dictionary(project_id: str, request: Request, body: s.DictionaryPreview,
                       actor: Principal = Depends(read)):
    return request.app.state.container.production.preview_dictionary(project_id, body.model_dump(), actor)


@router.post("/batches/analyze", response_model=s.AnalyzeResponse)
def analyze_batch(request: Request, body: s.BatchInput, actor: Principal = Depends(write)):
    return request.app.state.container.production.analyze_batch(body.model_dump(), actor)


@router.post("/batches", response_model=s.BatchResponse, status_code=202)
def create_batch(request: Request, body: s.BatchInput,
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 actor: Principal = Depends(write)):
    return request.app.state.container.production.create_batch(
        body.model_dump(), actor, idempotency_key=idempotency_key,
    )


@router.get("/batches", response_model=s.Page[s.BatchResponse])
def list_batches(request: Request, project_id: str | None = None,
                 limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                 actor: Principal = Depends(read)):
    return request.app.state.container.production.list_batches(
        actor, project_id=project_id, limit=limit, offset=offset,
    )


@router.get("/batches/{batch_id}", response_model=s.BatchResponse)
def get_batch(batch_id: str, request: Request, actor: Principal = Depends(read)):
    return request.app.state.container.production.get_batch(batch_id, actor)


@router.get("/batches/{batch_id}/items", response_model=s.Page[s.BatchItemResponse])
def batch_items(batch_id: str, request: Request, limit: int = Query(100, ge=1, le=200),
                offset: int = Query(0, ge=0), actor: Principal = Depends(read)):
    return request.app.state.container.production.batch_items(batch_id, actor, limit=limit, offset=offset)


@router.post("/batches/{batch_id}/retry-failed", response_model=s.BatchResponse)
def retry_failed(batch_id: str, request: Request, body: s.RetryFailed | None = None,
                 actor: Principal = Depends(write)):
    return request.app.state.container.production.retry_failed(
        batch_id, actor, item_ids=body.item_ids if body else None,
    )


@router.post("/batches/{batch_id}/cancel", response_model=s.BatchResponse)
def cancel_batch(batch_id: str, request: Request, actor: Principal = Depends(write)):
    return request.app.state.container.production.cancel_batch(batch_id, actor)


def _archive(service, actor, **kwargs):
    path = service.export(actor, **kwargs)
    return FileResponse(path, media_type="application/zip", filename="production-export.zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))


@router.get("/batches/{batch_id}/export", response_class=FileResponse,
            responses={200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}})
def export_batch(batch_id: str, request: Request, approved_only: bool = True,
                 actor: Principal = Depends(read)):
    return _archive(request.app.state.container.production, actor,
                    batch_id=batch_id, approved_only=approved_only)


@router.get("/projects/{project_id}/export", response_class=FileResponse,
            responses={200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}})
def export_project(project_id: str, request: Request, approved_only: bool = True,
                   actor: Principal = Depends(read)):
    return _archive(request.app.state.container.production, actor,
                    project_id=project_id, approved_only=approved_only)
