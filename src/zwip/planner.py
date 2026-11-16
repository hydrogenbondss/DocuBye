"""Field-mapping planners. The planner sees form metadata, never personal values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

PROFILE_FIELDS = {"full_name", "email", "phone"}


@dataclass(frozen=True, slots=True)
class FormField:
    name: str
    label: str
    input_type: str
    required: bool


@dataclass(frozen=True, slots=True)
class MappingPlan:
    mapping: dict[str, str]
    needs_human_help: bool = False
    reason: str = ""


class FieldPlanner(Protocol):
    def map_fields(self, fields: list[FormField]) -> MappingPlan: ...


class RuleBasedPlanner:
    """Predictable offline planner; the deterministic baseline for this milestone."""

    _labels = {
        "full name": "full_name",
        "name": "full_name",
        "email": "email",
        "email address": "email",
        "phone": "phone",
        "phone number": "phone",
        "telephone": "phone",
    }

    def map_fields(self, fields: list[FormField]) -> MappingPlan:
        mapping: dict[str, str] = {}
        seen_profile_fields: set[str] = set()
        for item in fields:
            profile_field = self._labels.get(item.label.strip().casefold())
            if not profile_field:
                if item.required:
                    return MappingPlan({}, True, "Required form field is not recognised")
                continue
            if profile_field in seen_profile_fields:
                return MappingPlan({}, True, "Multiple fields map to the same profile value")
            if profile_field not in PROFILE_FIELDS:
                return MappingPlan({}, True, "Field mapping is outside the allowed profile schema")
            mapping[item.name] = profile_field
            seen_profile_fields.add(profile_field)
        if any(item.required and item.name not in mapping for item in fields):
            return MappingPlan({}, True, "A required field could not be mapped")
        return MappingPlan(mapping)
