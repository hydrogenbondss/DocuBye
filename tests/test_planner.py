from zwip.planner import RuleBasedPlanner


def fixture_fields():
    from zwip.planner import FormField

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
    from zwip.planner import FormField

    fields = fixture_fields() + [FormField("government_id", "Government ID", "text", True)]
    result = RuleBasedPlanner().map_fields(fields)
    assert result.needs_human_help
    assert result.mapping == {}
