from __future__ import annotations

import importlib

import market_pulse.data as data
import market_pulse.rules as rules
import market_pulse.ui as ui


APP_VERSION = "ftd-persistence-v1"

if getattr(ui, "APP_VERSION", None) != APP_VERSION:
    rules = importlib.reload(rules)
    data = importlib.reload(data)
    ui = importlib.reload(ui)


if __name__ == "__main__":
    ui.main()
