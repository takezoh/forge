import os
from unittest.mock import patch

from config import get_api_key


class TestGetApiKey:
    def test_env_dict_oauth(self):
        env = {"LINEAR_OAUTH_TOKEN": "oauth"}
        assert get_api_key(env) == "oauth"

    @patch.dict(os.environ, {"LINEAR_OAUTH_TOKEN": "env-oauth"}, clear=True)
    def test_empty_env_falls_back_to_os(self):
        assert get_api_key({}) == "env-oauth"

    @patch.dict(os.environ, {"LINEAR_OAUTH_TOKEN": "env-oauth"}, clear=True)
    def test_none_env_reads_os(self):
        assert get_api_key(None) == "env-oauth"

    @patch.dict(os.environ, {}, clear=True)
    def test_nothing_returns_empty(self):
        assert get_api_key({}) == ""

    def test_oauth_empty_string_returns_empty(self):
        env = {"LINEAR_OAUTH_TOKEN": ""}
        assert get_api_key(env) == ""
