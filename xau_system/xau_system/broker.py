from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import requests

from .models import BrokerOrderResult, EntrySignal, Position, Side


class Broker(Protocol):
    def submit_bracket_order(self, signal: EntrySignal) -> BrokerOrderResult: ...
    def close_position(self, position: Position, close_price: float) -> BrokerOrderResult: ...


@dataclass(slots=True)
class PaperBroker:
    def submit_bracket_order(self, signal: EntrySignal) -> BrokerOrderResult:
        return BrokerOrderResult(accepted=True, order_id=str(uuid.uuid4()), fill_price=signal.entry_price, message="paper order accepted")

    def close_position(self, position: Position, close_price: float) -> BrokerOrderResult:
        return BrokerOrderResult(accepted=True, order_id=position.trade_id, fill_price=close_price, message="paper order closed")


@dataclass(slots=True)
class OandaBroker:
    token: str | None = None
    account_id: str | None = None
    env: str = "practice"

    def __post_init__(self) -> None:
        self.token = self.token or os.getenv("OANDA_API_TOKEN")
        self.account_id = self.account_id or os.getenv("OANDA_ACCOUNT_ID")
        self.env = os.getenv("OANDA_ENV", self.env)
        host = "api-fxpractice.oanda.com" if self.env == "practice" else "api-fxtrade.oanda.com"
        self.base_url = f"https://{host}/v3/accounts/{self.account_id}"

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def submit_bracket_order(self, signal: EntrySignal) -> BrokerOrderResult:
        if not self.token or not self.account_id:
            return BrokerOrderResult(accepted=False, message="Missing OANDA credentials")
        units = int(round(signal.lot_size * 100))
        if signal.side == Side.SHORT:
            units = -units
        payload = {
            "order": {
                "type": "MARKET",
                "instrument": signal.symbol,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": f"{signal.stop_price:.2f}"},
                "takeProfitOnFill": {"price": f"{signal.tp_price:.2f}"},
            }
        }
        try:
            r = requests.post(f"{self.base_url}/orders", headers=self.headers, json=payload, timeout=10)
            if not r.ok:
                return BrokerOrderResult(accepted=False, message=r.text)
            data = r.json()
            tx = data.get("orderFillTransaction", {})
            return BrokerOrderResult(accepted=True, order_id=str(tx.get("id")), fill_price=float(tx.get("price", signal.entry_price)), message="oanda order accepted")
        except requests.RequestException as exc:
            return BrokerOrderResult(accepted=False, message=str(exc))

    def close_position(self, position: Position, close_price: float) -> BrokerOrderResult:
        if not self.token or not self.account_id:
            return BrokerOrderResult(accepted=False, message="Missing OANDA credentials")
        long_short = "long" if position.side == Side.LONG else "short"
        payload = {long_short + "Units": "ALL"}
        try:
            r = requests.put(f"{self.base_url}/positions/{position.symbol}/close", headers=self.headers, json=payload, timeout=10)
            if not r.ok:
                return BrokerOrderResult(accepted=False, message=r.text)
            return BrokerOrderResult(accepted=True, order_id=position.trade_id, fill_price=close_price, message="oanda close submitted")
        except requests.RequestException as exc:
            return BrokerOrderResult(accepted=False, message=str(exc))
