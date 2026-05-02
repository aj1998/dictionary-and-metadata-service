"""Unit tests for YAML config validation against JSON Schema."""

import json
import copy
import pytest
import yaml
import jsonschema

YAML_PATH = "parser_configs/jainkosh.yaml"
SCHEMA_PATH = "parser_configs/_schemas/jainkosh.schema.json"


@pytest.fixture
def raw_config():
    with open(YAML_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def test_yaml_validates_against_schema(raw_config, schema):
    jsonschema.validate(raw_config, schema)


def test_missing_version_fails(raw_config, schema):
    bad = copy.deepcopy(raw_config)
    del bad["version"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_missing_block_classes_fails(raw_config, schema):
    bad = copy.deepcopy(raw_config)
    del bad["block_classes"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_load_config_succeeds():
    from workers.ingestion.jainkosh.config import load_config
    config = load_config()
    assert config.version == "1.1.0"
    assert config.parser_rules_version == "jainkosh.rules/1.2.0"
    assert config.envelope.idempotency_mode == "envelope_root"
    assert len(config.headings.variants) >= 4


def test_index_has_see_also_triggers(raw_config, schema):
    jsonschema.validate(raw_config, schema)
    assert "see_also_triggers" in raw_config["index"]
    assert isinstance(raw_config["index"]["see_also_triggers"], list)
    assert len(raw_config["index"]["see_also_triggers"]) >= 1


def test_index_has_see_also_window_chars(raw_config, schema):
    jsonschema.validate(raw_config, schema)
    assert "see_also_window_chars" in raw_config["index"]
    assert isinstance(raw_config["index"]["see_also_window_chars"], int)


def test_index_has_see_also_leading_punct_re(raw_config, schema):
    jsonschema.validate(raw_config, schema)
    assert "see_also_leading_punct_re" in raw_config["index"]
    assert isinstance(raw_config["index"]["see_also_leading_punct_re"], str)


def test_config_see_also_triggers_loaded(raw_config):
    from workers.ingestion.jainkosh.config import load_config
    config = load_config()
    assert "देखें" in config.index.see_also_triggers
    assert "विशेष देखें" in config.index.see_also_triggers
    assert config.index.see_also_window_chars >= 1
