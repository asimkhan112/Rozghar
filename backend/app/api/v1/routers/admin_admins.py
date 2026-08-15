"""Admin account and session management.

Everything here is gated on `ADMIN_MANAGE`, with role assignment additionally
requiring `ADMIN_ROLE_ASSIGN` — being able to create an account and being able
to decide what it can do are different powers, and a deployment may well want
them held by different people.

The router does no rule enforcement. "You cannot demote the last
administrator", "you cannot deactivate yourself", and "a role change revokes
live sessions" all live in the service, because all three have to hold when the
CLI or a future migration calls the same code.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.v1.deps import (
    DbSession,
    client_ip,
    get_permission_service,
    require,
)
from app.api.v1.mappers import admin_detail, admin_session_detail, paginate_admins
from app.core.permissions import Permission
from app.core.security import hash_ip
from app.repositories.admin_management_repo import AdminFilters
from app.schemas.admin import (
    AdminCreate,
    AdminDetail,
    AdminRead,
    AdminSessionDetail,
    AdminUpdate,
    PasswordResetConsume,
    PasswordResetIssued,
    RevocationResult,
    SessionRevokeRequest,
)
from app.schemas.common import Paginated
from app.services.admin_management_service import AdminManagementService
from app.services.auth_service import Principal
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/admin", tags=["admin:accounts"])


async def admin_service(
    session: DbSession,
    permissions: Annotated[PermissionService, Depends(get_permission_service)],
) -> AdminManagementService:
    """The permission service is injected so a role change can invalidate the
    RBAC cache in the same call that makes it."""
    return AdminManagementService(session, permissions=permissions)


ServiceDep = Annotated[AdminManagementService, Depends(admin_service)]
ManagerDep = Annotated[Principal, Depends(require(Permission.ADMIN_MANAGE))]


def _ip(request: Request) -> str | None:
    return hash_ip(client_ip(request))


# --- accounts -------------------------------------------------------------


@router.get("/admins", response_model=Paginated[AdminDetail], summary="List admin accounts")
async def list_admins(
    service: ServiceDep,
    _: ManagerDep,
    is_active: bool | None = None,
    role_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[AdminDetail]:
    result = await service.list(
        AdminFilters(is_active=is_active, role_id=role_id, search=search),
        page=page,
        per_page=per_page,
    )
    return paginate_admins(result)


@router.post(
    "/admins",
    response_model=AdminDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an admin account",
    responses={
        404: {"description": "Unknown role"},
        409: {"description": "Email already in use"},
    },
)
async def create_admin(
    payload: AdminCreate,
    request: Request,
    response: Response,
    service: ServiceDep,
    principal: Annotated[
        Principal, Depends(require(Permission.ADMIN_MANAGE, Permission.ADMIN_ROLE_ASSIGN))
    ],
) -> AdminDetail:
    """Creating an account assigns it a role, so this needs both permissions.
    There is no public registration path and never will be."""
    admin = await service.create(payload.model_dump(), principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    response.headers["Location"] = f"/api/v1/admin/admins/{admin.id}"
    return admin_detail(admin)


@router.get("/admins/{admin_id}", response_model=AdminDetail, summary="One admin account")
async def get_admin(admin_id: UUID, service: ServiceDep, _: ManagerDep) -> AdminDetail:
    return admin_detail(await service.get(admin_id))


@router.patch(
    "/admins/{admin_id}",
    response_model=AdminDetail,
    summary="Rename, activate, deactivate or change role",
    responses={
        403: {"description": "You cannot change your own role or deactivate yourself"},
        409: {"description": "This would leave nobody able to administer the platform"},
    },
)
async def update_admin(
    admin_id: UUID,
    payload: AdminUpdate,
    request: Request,
    service: ServiceDep,
    principal: ManagerDep,
) -> AdminDetail:
    """A role change is not an ordinary field edit: it revokes the account's
    sessions and bumps the permission cache, so the new grants take effect
    immediately rather than at the next token expiry."""
    changes = payload.model_dump(exclude_unset=True)
    if "role_id" in changes and not principal.has(Permission.ADMIN_ROLE_ASSIGN.value):
        from app.core.exceptions import PermissionDenied

        raise PermissionDenied(Permission.ADMIN_ROLE_ASSIGN.value)

    admin = await service.update(admin_id, changes, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return admin_detail(admin)


@router.delete(
    "/admins/{admin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an admin account",
    responses={409: {"description": "This would leave nobody able to administer the platform"}},
)
async def deactivate_admin(
    admin_id: UUID,
    request: Request,
    service: ServiceDep,
    principal: ManagerDep,
) -> Response:
    """Deactivates rather than deletes. `audit_logs.admin_id` and
    `jobs.created_by` reference this row — the latter with RESTRICT, so the
    database would refuse a delete anyway — and losing the account would orphan
    the record of what it did."""
    await service.deactivate(admin_id, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- passwords ------------------------------------------------------------


@router.post(
    "/admins/{admin_id}/password-reset",
    response_model=PasswordResetIssued,
    summary="Issue a single-use password reset token",
)
async def issue_password_reset(
    admin_id: UUID,
    request: Request,
    service: ServiceDep,
    principal: ManagerDep,
) -> PasswordResetIssued:
    """The token is returned **once** and stored only as a hash. Deliver it out
    of band; it cannot be shown again and expires in two hours."""
    issued = await service.issue_password_reset(admin_id, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return PasswordResetIssued(token=issued.token, expires_at=issued.expires_at)


@router.post(
    "/admins/password-reset/consume",
    response_model=AdminRead,
    summary="Redeem a reset token and set a new password",
    responses={400: {"description": "Token is invalid, expired, or already used"}},
)
async def consume_password_reset(
    payload: PasswordResetConsume,
    service: ServiceDep,
) -> AdminRead:
    """Unauthenticated by necessity — the holder cannot sign in, which is the
    situation this exists for. The token is the credential: single use, two
    hour lifetime, and redeeming it revokes every session the account had."""
    admin = await service.consume_password_reset(payload.token, payload.new_password)
    await service.session.commit()
    return AdminRead.model_validate(admin)


# --- sessions -------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=list[AdminSessionDetail],
    summary="Live admin sessions across the platform",
)
async def list_sessions(
    service: ServiceDep,
    _: ManagerDep,
    admin_id: UUID | None = None,
    active_only: bool = True,
) -> list[AdminSessionDetail]:
    """Carries the owning account's identity: this is the screen where an
    unfamiliar device gets spotted, and it is useless without knowing whose."""
    rows = await service.list_sessions(admin_id=admin_id, active_only=active_only)
    return [admin_session_detail(row, email, name) for row, email, name in rows]


@router.post(
    "/sessions/revoke",
    response_model=RevocationResult,
    summary="Revoke one session",
)
async def revoke_session(
    payload: SessionRevokeRequest,
    request: Request,
    service: ServiceDep,
    principal: ManagerDep,
) -> RevocationResult:
    """Idempotent — revoking an already-revoked session reports zero rather
    than failing."""
    revoked = await service.revoke_session(
        payload.session_id, principal=principal, ip_hash=_ip(request)
    )
    await service.session.commit()
    return RevocationResult(revoked=1 if revoked else 0)


@router.post(
    "/logout-all",
    response_model=RevocationResult,
    summary="Sign every admin out, including yourself",
)
async def logout_all(
    request: Request,
    service: ServiceDep,
    principal: ManagerDep,
) -> RevocationResult:
    """Break glass. Includes the caller deliberately: an operator who stays
    signed in while everyone else is ejected is describing a narrower action,
    and the exception would leave live exactly the session an attacker might be
    holding."""
    count = await service.logout_everyone(principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return RevocationResult(revoked=count)
