"""极简 `fastapi` 桩——**仅供本机无依赖时跑单测**。

只实现业务层与路由层实际用到的子集：
    HTTPException（status_code / detail）
    APIRouter（prefix + get/post/patch/delete 装饰器，记录路由表）
    Query / Body / Depends
    FastAPI（include_router，便于冒烟检查）

不实现真正的 ASGI 请求处理：HTTP 层由 `backend/tests`（第一部分）用 TestClient 覆盖，
第二部分的单测聚焦服务层逻辑（规则判定全在服务层，路由只是薄壳）。
"""

from __future__ import annotations

from typing import Any, Callable


class HTTPException(Exception):
    def __init__(
        self,
        status_code: int = 400,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(f"HTTP {status_code}: {detail}")


class APIRouter:
    def __init__(self, prefix: str = "", tags: list[str] | None = None, **kwargs: Any) -> None:
        self.prefix = prefix
        self.tags = tags or []
        self.routes: list[tuple[str, str, Callable[..., Any]]] = []

    def _route(self, method: str, path: str, **kwargs: Any):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routes.append((method, f"{self.prefix}{path}", func))
            return func

        return decorator

    def get(self, path: str, **kwargs: Any):
        return self._route("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any):
        return self._route("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any):
        return self._route("PATCH", path, **kwargs)

    def put(self, path: str, **kwargs: Any):
        return self._route("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any):
        return self._route("DELETE", path, **kwargs)


def Query(default: Any = None, **kwargs: Any) -> Any:  # noqa: N802
    return default


def Body(default: Any = None, **kwargs: Any) -> Any:  # noqa: N802
    return default


def Depends(dependency: Any = None) -> Any:  # noqa: N802
    return dependency


class FastAPI:
    def __init__(self, **kwargs: Any) -> None:
        self.title = kwargs.get("title", "stub")
        self.routes: list[tuple[str, str, Callable[..., Any]]] = []

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        self.routes.extend(router.routes)

    def get(self, path: str, **kwargs: Any):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routes.append(("GET", path, func))
            return func

        return decorator

    def post(self, path: str, **kwargs: Any):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routes.append(("POST", path, func))
            return func

        return decorator
