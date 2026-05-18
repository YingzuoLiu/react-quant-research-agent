import logging
from datetime import date, timedelta
from typing import Any, Dict, List

import baostock as bs

from ..base import BaseStep

logger = logging.getLogger(__name__)

_MOCK_PRICES = {"AAPL": 180, "MSFT": 420, "NVDA": 1100}


class MarketBarsStep(BaseStep):
    async def execute(self, config: Dict[str, Any], context: Any) -> Dict[str, Any]:
        symbols: List[str] = config.get("symbols", [])
        lookback_days: int = int(config.get("lookback_days", 5))

        if not isinstance(symbols, list):
            raise ValueError("symbols must be a list")
        if not symbols:
            raise ValueError("symbols list is empty")

        baostock_symbols = [s for s in symbols if s.startswith(("sh.", "sz."))]
        fallback_symbols = [s for s in symbols if s not in baostock_symbols]

        bars: Dict[str, Any] = {}

        # Fetch real bars from BaoStock for A-share symbols
        if baostock_symbols:
            end_date = date.today()
            start_date = end_date - timedelta(days=lookback_days * 3)
            login_result = bs.login()
            if login_result.error_code != "0":
                raise RuntimeError(
                    "BaoStock login failed: {0}".format(login_result.error_msg)
                )
            try:
                for symbol in baostock_symbols:
                    bars[symbol] = self._fetch_symbol(
                        symbol,
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d"),
                        lookback_days,
                    )
            finally:
                bs.logout()

        # Fall back to mock data for unrecognised symbols (e.g. AAPL, MSFT)
        for symbol in fallback_symbols:
            base = _MOCK_PRICES.get(symbol, 100)
            bars[symbol] = [
                {"date": "day_{0}".format(i + 1), "close": float(base + i * 2)}
                for i in range(lookback_days)
            ]

        return bars

    def _fetch_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        lookback_days: int,
    ) -> List[Dict[str, Any]]:
        result = bs.query_history_k_data_plus(
            symbol,
            fields="date,close",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        if result.error_code != "0":
            raise RuntimeError(
                "BaoStock query failed for {0}: {1}".format(
                    symbol, result.error_msg
                )
            )

        rows = []
        while result.next():
            row = result.get_row_data()
            date_str, close_str = row[0], row[1]
            if not close_str:
                logger.warning(
                    "Missing close price for %s on %s, skipping", symbol, date_str
                )
                continue
            rows.append({"date": date_str, "close": float(close_str)})

        rows = rows[-lookback_days:]

        if not rows:
            raise RuntimeError(
                "No bar data returned for {0} in range {1} to {2}".format(
                    symbol, start_date, end_date
                )
            )

        return rows
