"""极简 `pydantic` 桩——**仅供本机无依赖时跑单测**。

只实现第一部分 `backend/core/models.py` 实际用到的子集：
`BaseModel` / `Field(default, default_factory, ...)` / 属性读写 / `model_dump(mode=)`。

与真实 Pydantic 的**已知差异**（测试时需自觉遵守）：
    * 不做类型校验与强转（例如传字符串不会被转成 Enum）；
    * 不校验 Field 的 ge/le 等约束（如 round_no ∈ [1,5]）；
    * extra 字段会被直接接收，不报错。

因此第二部分的代码一律显式传枚举实例、显式把 round_no 限制在 1..5，
不依赖 Pydantic 的隐式行为；合并进仓库后行为只会更严格，不会更松。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


class FieldInfo:
    def __init__(self, default=UNSET, default_factory=None, **metadata: Any) -> None:
        self.default = default
        self.default_factory = default_factory
        self.metadata = metadata


def Field(default=UNSET, *, default_factory=None, **metadata: Any) -> FieldInfo:  # noqa: N802
    return FieldInfo(default=default, default_factory=default_factory, **metadata)


def _collect_fields(cls) -> dict[str, Any]:
    annotations: dict[str, Any] = {}
    for base in reversed(cls.__mro__[1:]):
        annotations.update(getattr(base, "__annotations__", {}) or {})
    annotations.update(cls.__dict__.get("__annotations__", {}) or {})
    # 下划线开头的都是内部字段（如 __fields__），不参与实例字段
    return {name: annotation for name, annotation in annotations.items() if not name.startswith("_")}


class BaseModel:
    """够用的最小可用实现。"""

    __fields__: dict[str, Any] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__fields__ = _collect_fields(cls)

    def __init__(self, **data: Any) -> None:
        for name in self.__fields__:
            if name in data:
                value = data.pop(name)
            else:
                value = self._default_for(name)
            object.__setattr__(self, name, value)
        for name, value in data.items():
            object.__setattr__(self, name, value)

    @classmethod
    def _default_for(cls, name: str) -> Any:
        class_value = getattr(cls, name, UNSET)
        if isinstance(class_value, FieldInfo):
            if class_value.default_factory is not None:
                return class_value.default_factory()
            if class_value.default is not UNSET:
                return class_value.default
            raise TypeError(f"{cls.__name__} 缺少必填字段：{name}")
        if class_value is UNSET:
            raise TypeError(f"{cls.__name__} 缺少必填字段：{name}")
        return class_value

    # ---------------------------------------------------------------- 导出
    def model_dump(self, *, mode: str = "python", **kwargs: Any) -> dict[str, Any]:
        return {
            name: _dump(getattr(self, name), mode)
            for name in self.__fields__
        }

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> "BaseModel":
        payload = {name: getattr(self, name) for name in self.__fields__}
        payload.update(update or {})
        return type(self)(**payload)

    # ---------------------------------------------------------------- 杂项
    def __repr__(self) -> str:
        body = ", ".join(f"{name}={getattr(self, name)!r}" for name in self.__fields__)
        return f"{type(self).__name__}({body})"

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and all(
            getattr(self, name) == getattr(other, name) for name in self.__fields__
        )


def _dump(value: Any, mode: str) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat() if mode == "json" else value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode=mode)
    if isinstance(value, (list, tuple)):
        return [_dump(item, mode) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item, mode) for key, item in value.items()}
    return value
