"""Base class for every request body.

Fuzzing (qa/mbt, pass 3) found that a single request with Infinity, 1e999 or 1e308 in a number field was stored, and
from then on every page that read the record answered 500 (JSON can't carry Infinity; cents rounding overflowed).
Integers above SQLite's 64-bit range crashed the insert. So every request body now refuses non-finite numbers and
numbers too large to be real, with a 422 that names the field.
"""
from pydantic import BaseModel as _PydanticBase, ConfigDict, model_validator

MAX_NUMBER = 1e12  # larger than any follower count, price or payout this app will see; well inside float/SQLite range


def _too_big(v, path="") -> str | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return path or "value" if abs(v) > MAX_NUMBER else None
    if isinstance(v, dict):
        for k, x in v.items():
            if (bad := _too_big(x, f"{path}.{k}" if path else str(k))):
                return bad
    if isinstance(v, (list, tuple)):
        for i, x in enumerate(v):
            if (bad := _too_big(x, f"{path}[{i}]")):
                return bad
    if isinstance(v, _PydanticBase):
        return _too_big(v.__dict__, path)
    return None


class BaseModel(_PydanticBase):
    model_config = ConfigDict(allow_inf_nan=False)

    @model_validator(mode="after")
    def _numbers_in_range(self):
        bad = _too_big(self.__dict__)
        if bad:
            raise ValueError(f"{bad}: that number is too large.")
        return self
