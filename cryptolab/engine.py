"""Simulate off-chain channel updates, challenge windows, stale-state disputes and conserved settlement."""

from .validation import integer, identifier, chronological
import hashlib, json


def commitment(channel, nonce, balances):
    payload = json.dumps(
        {"channel": channel, "nonce": nonce, "balances": balances},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(b"payment-channel-v1:" + payload).hexdigest()


class Channel:
    def __init__(self, config):
        self.id = identifier(config["id"])
        self.parties = [identifier(x) for x in config["parties"]]
        if len(self.parties) != 2 or len(set(self.parties)) != 2:
            raise ValueError("two distinct parties required")
        self.deposits = {p: integer(config["deposits"][p]) for p in self.parties}
        self.total = sum(self.deposits.values())
        self.delay = integer(config["challenge_period"], minimum=1)
        self.states = {0: dict(self.deposits)}
        self.latest = 0
        self.status = "open"
        self.closing = None
        self.deadline = None
        self.result = None

    def state(self, event):
        nonce = integer(event["nonce"], minimum=1)
        balances = event["balances"]
        if set(balances) != set(self.parties):
            raise ValueError("state parties mismatch")
        values = {p: integer(balances[p]) for p in self.parties}
        if sum(values.values()) != self.total:
            raise ValueError("state inflation")
        if set(event["approvals"]) != set(self.parties) or len(event["approvals"]) != 2:
            raise ValueError("both parties must attest")
        if event["commitment"] != commitment(self.id, nonce, values):
            raise ValueError("commitment mismatch")
        return nonce, values

    def apply(self, e):
        kind = e["type"]
        time = e["timestamp"]
        if kind == "update":
            if self.status != "open":
                raise ValueError("updates require open channel")
            nonce, values = self.state(e)
            if nonce <= self.latest:
                raise ValueError("nonce must increase")
            self.latest = nonce
            self.states[nonce] = values
        elif kind == "close":
            if self.status != "open" or e["actor"] not in self.parties:
                raise ValueError("invalid close")
            nonce = integer(e["nonce"])
            if nonce not in self.states:
                raise ValueError("unknown state")
            self.status = "challenging"
            self.closing = nonce
            self.deadline = time + self.delay
        elif kind == "challenge":
            if (
                self.status != "challenging"
                or time >= self.deadline
                or e["actor"] not in self.parties
            ):
                raise ValueError("invalid challenge window")
            nonce = integer(e["nonce"])
            if nonce not in self.states or nonce <= self.closing:
                raise ValueError("challenge must use newer known state")
            self.closing = nonce
        elif kind == "settle":
            if self.status != "challenging" or time < self.deadline:
                raise ValueError("cannot settle before deadline")
            self.result = dict(self.states[self.closing])
            self.status = "settled"
        else:
            raise ValueError("unknown channel event")
        return {
            "type": kind,
            "status": self.status,
            "latest_nonce": self.latest,
            "closing_nonce": self.closing,
            "deadline": self.deadline,
        }


def analyze(data):
    channel = Channel(data["channel"])
    events = [channel.apply(e) for e in chronological(data["events"])]
    return {
        "status": channel.status,
        "capacity": channel.total,
        "latest_nonce": channel.latest,
        "closing_nonce": channel.closing,
        "deadline": channel.deadline,
        "settlement": channel.result,
        "states": {
            str(n): {"balances": v, "commitment": commitment(channel.id, n, v)}
            for n, v in channel.states.items()
        },
        "events": events,
    }
