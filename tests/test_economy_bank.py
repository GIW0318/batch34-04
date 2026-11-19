import pytest

import economy_bank as eb

CONFIG = {
    "fee_bps": 100,
    "daily_notional": 500,
    "deposit_cap": 300,
    "withdraw_cap": 200,
    "interest_bps": 10,
}


def accounts():
    return {
        "alice": {"gold": 1000, "bank": 0, "items": {"ore": 10}},
        "bob": {"gold": 1000, "bank": 0, "items": {}},
        "carol": {"gold": 100, "bank": 5000, "items": {"ore": 5}},
    }


def bank(**cfg):
    conf = dict(CONFIG)
    conf.update(cfg)
    return eb.EconomyBank(accounts(), conf)


def test_sell_order_reserves_items():
    b = bank()
    b.place_order("o1", "alice", "sell", "ore", 100, 4, now=0)
    st = b.state()
    assert st["accounts"]["alice"]["items"]["ore"] == 6
    assert st["orders"]["o1"]["status"] == "open"
    assert st["orders"]["o1"]["remaining"] == 4


def test_buy_order_locks_gold():
    b = bank()
    b.place_order("o1", "bob", "buy", "ore", 100, 4, now=0)
    st = b.state()
    assert st["accounts"]["bob"]["gold"] == 596
    assert st["accounts"]["bob"]["locked"] == 404


def test_crossed_orders_settle():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 100, 4, now=0)
    b.place_order("b1", "bob", "buy", "ore", 100, 4, now=1)
    st = b.state()
    assert st["accounts"]["alice"]["gold"] == 1396
    assert st["accounts"]["alice"]["items"]["ore"] == 6
    assert st["accounts"]["bob"]["gold"] == 596
    assert st["accounts"]["bob"]["locked"] == 0
    assert st["accounts"]["bob"]["items"]["ore"] == 4
    assert st["fees_collected"] == 8
    assert st["orders"]["s1"]["status"] == "filled"


def test_price_priority_wins():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 120, 1, now=0)
    b.place_order("s2", "carol", "sell", "ore", 100, 1, now=1)
    b.place_order("b1", "bob", "buy", "ore", 120, 1, now=2)
    st = b.state()
    assert st["orders"]["b1"]["status"] == "filled"
    assert st["trades"][0]["price"] == 100
    assert st["trades"][0]["seller"] == "carol"
    assert st["accounts"]["carol"]["gold"] == 199
    assert st["accounts"]["carol"]["items"]["ore"] == 4


def test_partial_fill_keeps_remainder():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 100, 4, now=0)
    b.place_order("b1", "bob", "buy", "ore", 100, 2, now=1)
    st = b.state()
    assert st["orders"]["s1"]["status"] == "partial"
    assert st["orders"]["s1"]["remaining"] == 2
    assert st["accounts"]["alice"]["gold"] == 1198
    assert st["accounts"]["bob"]["items"]["ore"] == 2


def test_unfilled_buy_rests_with_lock():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 100, 4, now=0)
    b.place_order("b1", "bob", "buy", "ore", 100, 6, now=1)
    st = b.state()
    assert st["accounts"]["bob"]["gold"] == 394
    assert st["accounts"]["bob"]["locked"] == 202
    assert st["orders"]["b1"]["status"] == "open"
    assert st["orders"]["b1"]["remaining"] == 2


def test_insufficient_funds_rejected():
    b = bank()
    with pytest.raises(ValueError):
        b.place_order("b1", "bob", "buy", "ore", 200, 10, now=0)


def test_daily_notional_limit():
    b = bank()
    b.place_order("b1", "bob", "buy", "ore", 100, 4, now=0)
    with pytest.raises(ValueError):
        b.place_order("b2", "bob", "buy", "ore", 100, 2, now=1)


def test_sell_more_than_inventory_rejected():
    b = bank()
    with pytest.raises(ValueError):
        b.place_order("s1", "alice", "sell", "ore", 100, 11, now=0)


def test_duplicate_order_id_rejected():
    b = bank()
    b.place_order("o1", "alice", "sell", "ore", 100, 1, now=0)
    with pytest.raises(ValueError):
        b.place_order("o1", "bob", "buy", "ore", 100, 1, now=1)


def test_cancel_buy_refunds_lock():
    b = bank()
    b.place_order("b1", "bob", "buy", "ore", 100, 4, now=0)
    b.cancel_order("b1", "bob", now=1)
    st = b.state()
    assert st["accounts"]["bob"]["gold"] == 1000
    assert st["accounts"]["bob"]["locked"] == 0
    assert st["orders"]["b1"]["status"] == "cancelled"


def test_cancel_sell_returns_items():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 100, 4, now=0)
    b.cancel_order("s1", "alice", now=1)
    assert b.state()["accounts"]["alice"]["items"]["ore"] == 10


def test_cancel_by_other_player_rejected():
    b = bank()
    b.place_order("s1", "alice", "sell", "ore", 100, 1, now=0)
    with pytest.raises(ValueError):
        b.cancel_order("s1", "bob", now=1)


def test_bank_daily_caps():
    b = bank()
    b.deposit("alice", 300, now=0)
    with pytest.raises(ValueError):
        b.deposit("alice", 1, now=1)
    b.withdraw("alice", 200, now=2)
    with pytest.raises(ValueError):
        b.withdraw("alice", 1, now=3)
    st = b.state()
    assert st["accounts"]["alice"]["bank"] == 100
    assert st["accounts"]["alice"]["gold"] == 900


def test_interest_accrues_per_full_day():
    b = bank()
    b.accrue(86400)
    assert b.state()["accounts"]["carol"]["bank"] == 5005
    b.accrue(86400)
    assert b.state()["accounts"]["carol"]["bank"] == 5005
    b.accrue(172800)
    assert b.state()["accounts"]["carol"]["bank"] == 5010
