import pytest
from fastapi.testclient import TestClient

from xleuth_api.main import create_app
from tests.test_auth_flow import MockDynamicAuthHandler


@pytest.fixture
def app():
    app = create_app()
    # Replace with mock for testing
    app.state.dynamic_auth_handler = MockDynamicAuthHandler()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)