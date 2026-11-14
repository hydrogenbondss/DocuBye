import json
import sys
from types import SimpleNamespace

from docubye.planner import FormField, OpenAIFieldPlanner


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.call = None

    def create(self, **kwargs):
        self.call = kwargs
        return SimpleNamespace(output_text=json.dumps(self.output))


class FakeOpenAI:
    response = None

    def __init__(self, api_key):
        self.responses = type(self).response


def _fake_module(output):
    fake_responses = FakeResponses(output)
    FakeOpenAI.response = fake_responses
    return SimpleNamespace(OpenAI=FakeOpenAI), fake_responses


def test_ai_planner_sends_only_field_metadata_and_validates_mapping(monkeypatch):
    module, fake_responses = _fake_module({
        "matches": [
            {"input_name": "person", "profile_field": "full_name"},
            {"input_name": "mail", "profile_field": "email"},
            {"input_name": "phone", "profile_field": "phone"},
        ],
        "needs_human_help": False,
    })
    monkeypatch.setitem(sys.modules, "openai", module)
    fields = [
        FormField("person", "Full name", "text", True),
        FormField("mail", "Email address", "email", True),
        FormField("phone", "Phone number", "tel", True),
    ]
    result = OpenAIFieldPlanner(api_key="test-key", model="test-model").map_fields(fields)
    assert result.mapping == {"person": "full_name", "mail": "email", "phone": "phone"}
    assert not result.needs_human_help
    assert "Alex Example" not in fake_responses.call["input"]
    assert "alex.example@example.test" not in fake_responses.call["input"]


def test_ai_planner_rejects_unlisted_input_name(monkeypatch):
    module, _ = _fake_module({
        "matches": [{"input_name": "password", "profile_field": "email"}],
        "needs_human_help": False,
    })
    monkeypatch.setitem(sys.modules, "openai", module)
    result = OpenAIFieldPlanner(api_key="test-key", model="test-model").map_fields(
        [FormField("mail", "Email", "email", True)]
    )
    assert result.needs_human_help
    assert result.mapping == {}
