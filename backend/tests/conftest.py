import pytest

from clearance_gap.catalog import Catalog
from clearance_gap.config import Settings
from clearance_gap.decisions import DecisionClient
from clearance_gap.engine import Engine
from clearance_gap.store import Store


@pytest.fixture
def config(tmp_path):
    return Settings(_env_file=None, database_path=str(tmp_path / "test.db"), fixture_delay_seconds=0)


@pytest.fixture
def engine(config):
    return Engine(config, Store(config), Catalog(config), DecisionClient(config))


@pytest.fixture
def request_body():
    return {"scenarioId": "incorrect-readback", "scenarioVersion": "1", "preset": "partial", "playback": "typed"}
