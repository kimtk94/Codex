from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    toss_client_id: str = ''
    toss_client_secret: str = ''
    toss_account: str = ''
    hub_gateway_secret: str = ''
    expected_egress_ip: str = ''

    trading_enabled: bool = False
    live_micro_total_limit_krw: int = 30000
    max_single_order_krw: int = 5000
    qqq_limit_krw: int = 10000
    nvda_limit_krw: int = 10000
    ionq_limit_krw: int = 10000
    allow_symbols: str = 'QQQ,NVDA,IONQ'

    host: str = '0.0.0.0'
    port: int = 8787

    @property
    def allowed_symbols(self) -> set[str]:
        return {s.strip().upper() for s in self.allow_symbols.split(',') if s.strip()}

    def symbol_limit_krw(self, symbol: str) -> int:
        limits = {
            'QQQ': self.qqq_limit_krw,
            'NVDA': self.nvda_limit_krw,
            'IONQ': self.ionq_limit_krw,
        }
        return limits.get(symbol.upper(), 0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
