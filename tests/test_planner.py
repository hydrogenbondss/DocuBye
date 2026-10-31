import pytest

from docubye.planner import FormField, OpenAIFieldPlanner, RuleBasedPlanner


def fixture_fields():
    return [
        FormField("full_name", "Full name", "text", True),
        FormField("email", "Email address", "email", True),
        FormField("phone", "Phone number", "tel", True),
    ]


def test_rule_based_planner_maps_known_fields():
    result = RuleBasedPlanner().map_fields(fixture_fields())
    assert not result.needs_human_help
    assert result.mapping == {
        "full_name": "full_name",
        "email": "email",
        "phone": "phone",
    }


def test_rule_based_planner_pauses_for_unknown_required_field():
    fields = fixture_fields() + [FormField("government_id", "Government ID", "text", True)]
    result = RuleBasedPlanner().map_fields(fields)
    assert result.needs_human_help
    assert result.mapping == {}


def test_ai_planner_requires_explicit_credentials_and_model(monkeypatch):
    monkeypatch.delenv("DOCUBYE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DOCUBYE_OPENAI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="DOCUBYE_OPENAI_API_KEY"):
        OpenAIFieldPlanner()
