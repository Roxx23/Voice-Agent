from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Shopify
    shopify_shop_domain: str = ""
    shopify_access_token: str = ""
    shopify_webhook_secret: str = ""

    # Vapi
    vapi_api_key: str = ""
    vapi_phone_number_id: str = ""
    vapi_assistant_id: str = ""

    # Groq
    groq_api_key: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./voiceagent.db"

    # App
    app_base_url: str = "http://localhost:8000"

    # Business rules
    discount_tier_1: int = 10
    discount_tier_2: int = 15
    call_window_start_hour: int = 9   # 9 AM IST
    call_window_end_hour: int = 21    # 9 PM IST
    max_concurrent_calls: int = 5
    abandonment_delay_minutes: int = 30
    retry_delay_hours: int = 2


settings = Settings()
