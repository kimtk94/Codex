from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    toss_client_id: str = ''
    toss_client_secret: str = ''
    toss_account: str = ''
    hub_gateway_secret: str = ''
    expected_egress_ip: str = ''
    toss_token_cache: str = '/opt/kalman/state/toss_oauth_token.json'

    # Automated live gate. Kept separate from manual broker access so
    # research/SHADOW automation can stay isolated while manual trading is armed.
    trading_enabled: bool = False
    live_trading_confirm: str = ''

    # Manual live gate. /api/orders/live uses this gate only.
    manual_trading_enabled: bool = False
    manual_trading_confirm: str = ''

    live_micro_total_limit_krw: int = 30000
    max_single_order_krw: int = 5000
    trading_state_db: str = '/opt/kalman/state/trading.sqlite3'
    shadow_bakeoff_status: str = '/mnt/gdrive/Market_Model_V2/shadow_bakeoff/v1/latest/bakeoff_status.json'

    host: str = '0.0.0.0'
    port: int = 8787

    @property
    def live_gate_open(self) -> bool:
        return self.trading_enabled and self.live_trading_confirm == 'CONFIRM_LIVE_TRADING'

    @property
    def manual_live_gate_open(self) -> bool:
        return (
            self.manual_trading_enabled
            and self.manual_trading_confirm == 'CONFIRM_MANUAL_TRADING'
        )

    @property
    def state_db_path(self) -> Path:
        return Path(self.trading_state_db).expanduser()

    @property
    def toss_token_cache_path(self) -> Path:
        return Path(self.toss_token_cache).expanduser()

    @property
    def shadow_bakeoff_status_path(self) -> Path:
        return Path(self.shadow_bakeoff_status).expanduser()

@lru_cache
def get_settings() -> Settings:
    return Settings()
