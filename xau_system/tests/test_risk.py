from xau_system.config import DEFAULT_CONFIG, DEFAULT_TIERS
from xau_system.risk import RiskManager


def test_lot_size_tier_cap_binds():
    rm = RiskManager(DEFAULT_CONFIG, DEFAULT_TIERS)
    lot = rm.calc_lot_size(account_balance=1000, stop_points=400)
    assert lot == 0.02


def test_stop_validation():
    rm = RiskManager(DEFAULT_CONFIG, DEFAULT_TIERS)
    valid, mn, mx = rm.validate_stop_distance(350, 120)
    assert valid is True
    assert mn == 300
    assert mx == 800
