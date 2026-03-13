# tests/test_universe_profiles.py
import pytest
import yaml
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.history import load_universe, get_profiles

@pytest.fixture
def mock_yaml_load(monkeypatch):
    """Mock the yaml.safe_load and builtins.open to return custom dict."""
    def _mock(content_dict):
        def mock_load(f):
            return content_dict
        monkeypatch.setattr(yaml, "safe_load", mock_load)
        
        # Mock open to just return a dummy context manager reading this file
        from unittest.mock import mock_open
        monkeypatch.setattr("builtins.open", mock_open(read_data=""))
    return _mock


@pytest.mark.parametrize(
    "yaml_content, expected_len, expected_first, expected_profiles_len, expected_default",
    [
        (
            {"assets": [{"xtb_ticker": "ABC"}, {"xtb_ticker": "DEF"}]},
            2, "ABC", 1, "legacy"
        ),
        (
            {
                "default_profile": "prof1",
                "profiles": {
                    "prof1": {"label": "Profile 1", "assets": [{"xtb_ticker": "T1"}]},
                    "prof2": {"label": "Profile 2", "assets": [{"xtb_ticker": "T2"}, {"xtb_ticker": "T3"}]}
                }
            },
            1, "T1", 2, "prof1"
        )
    ]
)
def test_schema_parsing(mock_yaml_load, yaml_content, expected_len, expected_first, expected_profiles_len, expected_default):
    mock_yaml_load(yaml_content)
    
    universe = load_universe()
    assert len(universe) == expected_len
    assert universe[0]["xtb_ticker"] == expected_first
    
    profiles, default = get_profiles()
    assert len(profiles) == expected_profiles_len
    assert default == expected_default


def test_actual_universe_profiles_include_requested_portfolios():
    profiles, default_profile = get_profiles()

    assert default_profile == "wide_portfolio"
    assert "wide_portfolio" in profiles
    assert "narrow_portfolio" in profiles
    assert profiles["wide_portfolio"]["label"] == "Wide Portfolio"
    assert profiles["narrow_portfolio"]["label"] == "Narrow Portfolio"

    wide_assets = {asset["xtb_ticker"]: asset for asset in load_universe("wide_portfolio")}
    narrow_tickers = [asset["xtb_ticker"] for asset in load_universe("narrow_portfolio")]

    assert {"NUKL", "SPYN"}.issubset(wide_assets)
    assert wide_assets["NUKL"]["isin"] == "IE000M7V94E1"
    assert wide_assets["SPYN"]["isin"] == "IE00BKWQ0F09"
    assert narrow_tickers == ["4GLD", "BTCE", "SXR8", "EXSA", "XEON", "XDW0", "CBUX", "XDWH", "AMEM"]
