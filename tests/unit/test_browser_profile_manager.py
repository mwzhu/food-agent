from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from shopper.config import Settings
from shopper.services.browser_profile_manager import BrowserProfileSyncUnavailableError, BrowserUseCloudProfileManager


class _FakeSession:
    def __init__(self) -> None:
        self.id = "session-123"
        self.live_url = "https://live.browser-use.com/fake"
        self.timeout_at = datetime.now(timezone.utc)


class _TimeoutThenSuccessManager(BrowserUseCloudProfileManager):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.disable_proxy_calls: list[bool] = []

    def _require_sdk(self) -> None:
        return None

    def _build_sdk_client(self):
        return object()

    async def _create_browser_session_request(self, client, *, disable_proxy: bool = False, store: str | None = None):
        self.disable_proxy_calls.append(disable_proxy)
        if not disable_proxy:
            raise httpx.ReadTimeout("timed out")
        return _FakeSession()


class _AlwaysTimeoutManager(BrowserUseCloudProfileManager):
    def _require_sdk(self) -> None:
        return None

    def _build_sdk_client(self):
        return object()

    async def _create_browser_session_request(self, client, *, disable_proxy: bool = False, store: str | None = None):
        raise httpx.ReadTimeout("timed out")


class _CaptureProxyModeManager(BrowserUseCloudProfileManager):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.disable_proxy_calls: list[bool] = []

    def _require_sdk(self) -> None:
        return None

    def _build_sdk_client(self):
        return object()

    async def _create_browser_session_request(self, client, *, disable_proxy: bool = False, store: str | None = None):
        self.disable_proxy_calls.append(disable_proxy)
        return _FakeSession()


class _LocalChatGPTManager(BrowserUseCloudProfileManager):
    def _require_playwright(self) -> None:
        return None

    async def _run_local_chatgpt_sync_browser(self, profile_dir, timeout_seconds: int) -> None:
        return None


def _settings(*, proxy_country_code: str | None = "us") -> Settings:
    return Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROFILE_ID="profile-123",
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE=proxy_country_code,
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )


def test_profile_manager_retries_without_proxy_on_timeout():
    manager = _TimeoutThenSuccessManager(_settings())

    session = asyncio.run(manager.create_instacart_sync_session())

    assert session.live_url == "https://live.browser-use.com/fake"
    assert manager.disable_proxy_calls == [False, True]


def test_profile_manager_timeout_without_proxy_config_reports_clean_error():
    manager = _AlwaysTimeoutManager(_settings(proxy_country_code=None))

    try:
        asyncio.run(manager.create_instacart_sync_session())
    except BrowserProfileSyncUnavailableError as exc:
        assert "timed out while creating the live session" in str(exc).lower()
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected BrowserProfileSyncUnavailableError to be raised.")


def test_chatgpt_profile_manager_skips_proxy_by_default():
    manager = _LocalChatGPTManager(_settings())

    session = asyncio.run(manager.create_chatgpt_sync_session())

    assert session.provider == "local_browser"
    assert session.live_url == "https://chatgpt.com/"
