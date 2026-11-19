import pytest

import server_migration as sm

SERVERS = {"s1": {"slots": 3}, "s2": {"slots": 3}, "s3": {"slots": 1}}
CHARS = {
    "alice": {"server": "s1", "inventory": {"gem": 2, "sword": 1}},
    "bob": {"server": "s1", "inventory": {"axe": 1}},
}


def make(**cfg):
    base = {"carry": 2, "mail_ttl": 10, "lockout": 5}
    base.update(cfg)
    chars = {}
    for name, data in CHARS.items():
        chars[name] = {"server": data["server"], "inventory": dict(data["inventory"])}
    return sm.ServerMigration({k: dict(v) for k, v in SERVERS.items()}, chars, base)


def test_request_creates_pending_transfer():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    st = m.state()
    assert st["transfers"]["t1"]["status"] == "pending"
    assert st["transfers"]["t1"]["from"] == "s1"
    assert st["transfers"]["t1"]["to"] == "s2"
    assert st["characters"]["alice"]["pending"] == "t1"
    assert st["characters"]["alice"]["inventory"] == {"gem": 2, "sword": 1}


def test_unknown_character_rejected():
    m = make()
    with pytest.raises(ValueError):
        m.request("t1", "ghost", "s2", now=0)


def test_bad_target_rejected():
    m = make()
    with pytest.raises(ValueError):
        m.request("t1", "alice", "s9", now=0)
    with pytest.raises(ValueError):
        m.request("t1", "alice", "s1", now=0)


def test_duplicate_transfer_id_rejected():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    with pytest.raises(ValueError):
        m.request("t1", "bob", "s3", now=0)


def test_second_transfer_while_pending_rejected():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    with pytest.raises(ValueError):
        m.request("t2", "alice", "s3", now=1)


def test_target_slot_reservation_counts_pending():
    m = make()
    m.request("t1", "alice", "s3", now=0)
    with pytest.raises(ValueError):
        m.request("t2", "bob", "s3", now=1)


def test_confirm_moves_character_and_mails_overflow():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.confirm("t1", now=3)
    st = m.state()
    assert st["transfers"]["t1"]["status"] == "completed"
    assert st["characters"]["alice"]["server"] == "s2"
    assert st["characters"]["alice"]["inventory"] == {"gem": 2}
    assert st["characters"]["alice"]["pending"] is None
    mails = st["mailboxes"]["alice"]
    assert len(mails) == 1
    assert mails[0]["items"] == {"sword": 1}
    assert mails[0]["expires"] == 13
    assert mails[0]["status"] == "unread"


def test_confirm_applies_lockout():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.confirm("t1", now=3)
    assert m.state()["characters"]["alice"]["lock_until"] == 8
    with pytest.raises(ValueError):
        m.request("t2", "alice", "s3", now=7)
    m.request("t2", "alice", "s3", now=8)


def test_expired_transfer_cannot_confirm():
    m = make()
    m.request("t1", "alice", "s2", now=0, ttl=5)
    with pytest.raises(ValueError):
        m.confirm("t1", now=6)


def test_expire_frees_target_reservation():
    m = make()
    m.request("t1", "alice", "s3", now=0, ttl=5)
    m.expire(6)
    st = m.state()
    assert st["transfers"]["t1"]["status"] == "expired"
    assert st["characters"]["alice"]["pending"] is None
    m.request("t2", "bob", "s3", now=6)


def test_cancel_allows_new_transfer():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.cancel("t1", now=1)
    assert m.state()["transfers"]["t1"]["status"] == "cancelled"
    m.request("t2", "alice", "s2", now=2)


def test_claim_delivers_mail_items():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.confirm("t1", now=3)
    mail_id = m.state()["mailboxes"]["alice"][0]["mail_id"]
    m.claim("alice", mail_id, now=4)
    st = m.state()
    assert st["characters"]["alice"]["inventory"] == {"gem": 2, "sword": 1}
    assert st["mailboxes"]["alice"][0]["status"] == "claimed"


def test_claim_twice_rejected():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.confirm("t1", now=3)
    mail_id = m.state()["mailboxes"]["alice"][0]["mail_id"]
    m.claim("alice", mail_id, now=4)
    with pytest.raises(ValueError):
        m.claim("alice", mail_id, now=5)


def test_expired_mail_cannot_be_claimed():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    m.confirm("t1", now=3)
    mail_id = m.state()["mailboxes"]["alice"][0]["mail_id"]
    m.expire(20)
    with pytest.raises(ValueError):
        m.claim("alice", mail_id, now=21)


def test_state_is_deep_copy():
    m = make()
    m.request("t1", "alice", "s2", now=0)
    st = m.state()
    st["characters"]["alice"]["inventory"]["gem"] = 99
    st["transfers"]["t1"]["status"] = "hacked"
    assert m.state()["characters"]["alice"]["inventory"]["gem"] == 2
    assert m.state()["transfers"]["t1"]["status"] == "pending"
