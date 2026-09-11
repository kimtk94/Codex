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

    # Two-key live gate. Both must be satisfied.
    trading_enabled: bool = False
    live_trading_confirm: str = ''

    live_micro_total_limit_krw: int = 30000
    max_single_order_krw: int = 5000
    trading_state_db: str = '/opt/kalman/state/trading.sqlite3'

    host: str = '0.0.0.0'
    port: int = 8787

    @property
    def live_gate_open(self) -> bool:
        return self.trading_enabled and self.live_trading_confirm == 'CONFIRM_LIVE_TRADING'

    @property
    def state_db_path(self) -> Path:
        return Path(self.trading_state_db).expanduser()

    @property
    def toss_token_cache_path(self) -> Path:
        return Path(self.toss_token_cache).expanduser()

@lru_cache
def get_settings() -> Settings:
    return Settings()
