from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from .models import EntrySignal


@dataclass(slots=True)
class AlertManager:
    bot_token: str | None = None
    chat_id: str | None = None

    def __post_init__(self) -> None:
        self.bot_token = self.bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = self.chat_id or os.getenv("TELEGRAM_CHAT_ID")

    def send(self, text: str) -> None:
        print(text)
        if not self.bot_token or not self.chat_id:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            requests.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=10)
        except requests.RequestException:
            pass

    def send_signal(self, signal: EntrySignal) -> None:
        self.send(
            f"{signal.symbol} {signal.side.value.upper()} | session={signal.session.value} | entry={signal.entry_price:.2f} | stop={signal.stop_price:.2f} | tp={signal.tp_price:.2f} | lot={signal.lot_size:.2f} | rr={signal.rr_multiple:.2f} | level={signal.level.label}"
        )
