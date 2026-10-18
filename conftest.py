"""Shared test setup: every test starts with empty fake Databrokers and a fresh fake Zenoh bus."""

import pytest

from fakes import kuksa as fake_kuksa
from fakes import zenoh as fake_zenoh


@pytest.fixture(autouse=True)
def clean_fakes():
    fake_kuksa.reset()
    fake_zenoh.reset()
    fake_zenoh.configure(delay_ms=5, jitter_ms=2, seed=1)
    yield
    fake_zenoh.reset()
