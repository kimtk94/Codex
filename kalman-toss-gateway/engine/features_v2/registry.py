from __future__ import annotations

FEATURE_SET = "market_tools_v2_001"

FEATURES = [
    {"name": "talib_v2_rsi14", "library": "TA-Lib", "function": "RSI", "lookback": 14},
    {"name": "talib_v2_macd", "library": "TA-Lib", "function": "MACD", "lookback": "12,26,9"},
    {"name": "talib_v2_macd_signal", "library": "TA-Lib", "function": "MACD", "lookback": "12,26,9"},
    {"name": "talib_v2_macd_hist", "library": "TA-Lib", "function": "MACD", "lookback": "12,26,9"},
    {"name": "talib_v2_adx14", "library": "TA-Lib", "function": "ADX", "lookback": 14},
    {"name": "talib_v2_atr14", "library": "TA-Lib", "function": "ATR", "lookback": 14},
    {"name": "talib_v2_natr14", "library": "TA-Lib", "function": "NATR", "lookback": 14},
    {"name": "talib_v2_roc10", "library": "TA-Lib", "function": "ROC", "lookback": 10},
    {"name": "talib_v2_obv", "library": "TA-Lib", "function": "OBV", "lookback": None},
    {"name": "talib_v2_bb_upper", "library": "TA-Lib", "function": "BBANDS", "lookback": 20},
    {"name": "talib_v2_bb_mid", "library": "TA-Lib", "function": "BBANDS", "lookback": 20},
    {"name": "talib_v2_bb_lower", "library": "TA-Lib", "function": "BBANDS", "lookback": 20},
    {"name": "talib_v2_bb_pctb", "library": "TA-Lib", "function": "BBANDS", "lookback": 20},
]


def registry_payload() -> dict:
    return {
        "feature_set": FEATURE_SET,
        "point_in_time": True,
        "production_compatible": False,
        "shadow_only": True,
        "features": FEATURES,
    }
