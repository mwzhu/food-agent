from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

import httpx

from shopper.config import Settings
from shopper.schemas import BrowserProfileSyncSession, BrowserProfileSyncStatus


WALMART_LOGIN_URL = "https://www.walmart.com/account/login"
WALMART_GROCERY_START_URL = "https://www.walmart.com/cp/grocery/976759"
INSTACART_LOGIN_URL = "https://www.instacart.com/login"
INSTACART_GROCERY_START_URL = "https://www.instacart.com/grocery-delivery"
CHATGPT_LOGIN_URL = "https://chatgpt.com/auth/login"
CHATGPT_START_URL = "https://chatgpt.com/"

logger = logging.getLogger(__name__)
SDK_REQUEST_TIMEOUT_SECONDS = 45


class BrowserProfileSyncUnavailableError(RuntimeError):
    """Raised when Browser Use cloud profile sync cannot be used in this environment."""


@dataclass(frozen=True)
class StoreProfileConfig:
    key: str
    display_name: str
    profile_name: str
    login_url: str
    start_url: str
    cookie_domain_fragment: str
    use_cloud_proxy: bool = True


STORE_PROFILE_CONFIGS = {
    "walmart": StoreProfileConfig(
        key="walmart",
        display_name="Walmart",
        profile_name="shopper-walmart-checkout",
        login_url=WALMART_LOGIN_URL,
        start_url=WALMART_GROCERY_START_URL,
        cookie_domain_fragment="walmart.com",
    ),
    "instacart": StoreProfileConfig(
        key="instacart",
        display_name="Instacart",
        profile_name="shopper-instacart-checkout",
        login_url=INSTACART_LOGIN_URL,
        start_url=INSTACART_GROCERY_START_URL,
        cookie_domain_fragment="instacart.com",
    ),
    "chatgpt": StoreProfileConfig(
        key="chatgpt",
        display_name="ChatGPT",
        profile_name="shopper-chatgpt-checkout",
        login_url=CHATGPT_LOGIN_URL,
        start_url=CHATGPT_START_URL,
        cookie_domain_fragment="chatgpt.com",
        use_cloud_proxy=False,
    ),
}


def browser_use_sdk_runtime_status() -> tuple[bool, Optional[str]]:
    if tuple(int(part) for part in platform.python_version_tuple()[:2]) < (3, 11):
        return False, "Browser Use cloud profile sync requires Python 3.11 or newer."

    try:
        import browser_use_sdk  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on runtime install
        return False, f"browser_use_sdk is not installed or failed to import: {exc}"

    return True, None


def is_cloud_session_limit_error(error: Exception) -> bool:
    message = str(error).lower()
    return "concurrent sessions reached" in message or "free plan limit" in message


async def stop_active_cloud_browser_sessions(settings: Settings) -> int:
    available, _ = browser_use_sdk_runtime_status()
    if not available or not settings.browser_use_api_key:
        return 0

    from browser_use_sdk import AsyncBrowserUse

    client = AsyncBrowserUse(api_key=settings.browser_use_api_key)
    sessions = await client.browsers.list_browser_sessions(filter_by="active", page_size=20)
    stopped = 0
    for session in sessions.items:
        try:
            await client.browsers.update_browser_session(session.id, action="stop")
        except Exception as exc:  # pragma: no cover - depends on Browser Use API behavior
            logger.warning("Failed to stop Browser Use cloud session %s: %s", session.id, exc)
            continue
        stopped += 1
    return stopped


class BrowserUseCloudProfileManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._local_sync_tasks: dict[str, asyncio.Task] = {}

    def _base_status(
        self,
        store: str,
        *,
        configured: bool,
        ready: bool,
        message: str,
        provider: Literal["browser_use_cloud", "local_browser"] = "browser_use_cloud",
        profile_id: str | None = None,
        profile_name: str | None = None,
    ) -> BrowserProfileSyncStatus:
        config = STORE_PROFILE_CONFIGS[store]
        return BrowserProfileSyncStatus(
            store=config.display_name,
            provider=provider,
            configured=configured,
            ready=ready,
            profile_id=profile_id if profile_id is not None else self.settings.browser_checkout_cloud_profile_id,
            profile_name=profile_name
            if profile_name is not None
            else (config.profile_name if self.settings.browser_checkout_cloud_profile_id else None),
            login_url=config.login_url,
            start_url=config.start_url,
            message=message,
        )

    @staticmethod
    def _require_playwright() -> None:
        if tuple(int(part) for part in platform.python_version_tuple()[:2]) < (3, 11):
            raise BrowserProfileSyncUnavailableError("Local ChatGPT profile sync requires Python 3.11 or newer.")
        try:
            import playwright.async_api  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on runtime install
            raise BrowserProfileSyncUnavailableError(f"Playwright is not installed or failed to import: {exc}") from exc

    def _chatgpt_local_profile_dir(self) -> Path:
        if self.settings.browser_checkout_user_data_dir:
            return Path(self.settings.browser_checkout_user_data_dir).expanduser()
        return Path(self.settings.checkout_artifacts_dir).parent / "browser_profiles" / "chatgpt"

    async def _chatgpt_local_ready(self) -> bool:
        self._require_playwright()
        profile_dir = self._chatgpt_local_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=True,
            )
            try:
                cookies = await context.cookies("https://chatgpt.com")
                return any("chatgpt.com" in (cookie.get("domain") or "") for cookie in cookies)
            finally:
                await context.close()

    async def _run_local_chatgpt_sync_browser(self, profile_dir: Path, timeout_seconds: int) -> None:
        self._require_playwright()

        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        try:
            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    headless=False,
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(CHATGPT_START_URL)

                    closed = asyncio.get_running_loop().create_future()

                    def _mark_closed(*_args) -> None:
                        if not closed.done():
                            closed.set_result(None)

                    context.on("close", _mark_closed)

                    try:
                        await asyncio.wait_for(closed, timeout=timeout_seconds)
                    except asyncio.TimeoutError:
                        logger.info("Local ChatGPT sync window timed out after %s seconds; closing it.", timeout_seconds)
                finally:
                    try:
                        await context.close()
                    except PlaywrightError:
                        pass
        except Exception as exc:  # pragma: no cover - depends on local browser availability
            logger.warning("Local ChatGPT sync browser failed: %s", exc)

    async def _get_chatgpt_status(self) -> BrowserProfileSyncStatus:
        profile_dir = self._chatgpt_local_profile_dir()
        try:
            ready = await self._chatgpt_local_ready()
        except BrowserProfileSyncUnavailableError as exc:
            return self._base_status(
                "chatgpt",
                configured=False,
                ready=False,
                message=str(exc),
                provider="local_browser",
                profile_id=str(profile_dir),
                profile_name="chatgpt-local-profile",
            )
        except Exception as exc:
            return self._base_status(
                "chatgpt",
                configured=True,
                ready=False,
                message=f"Could not read the local ChatGPT browser profile yet: {exc}",
                provider="local_browser",
                profile_id=str(profile_dir),
                profile_name="chatgpt-local-profile",
            )

        return BrowserProfileSyncStatus(
            store="ChatGPT",
            provider="local_browser",
            configured=True,
            ready=ready,
            profile_id=str(profile_dir),
            profile_name="chatgpt-local-profile",
            login_url=CHATGPT_LOGIN_URL,
            start_url=CHATGPT_START_URL,
            cookie_domains=["chatgpt.com"] if ready else [],
            last_used_at=None,
            message=(
                "ChatGPT cookies were found in the local browser profile."
                if ready
                else "No ChatGPT cookies were found yet. Open the local sync browser and sign in once."
            ),
        )

    async def _create_chatgpt_local_sync_session(self) -> BrowserProfileSyncSession:
        self._require_playwright()
        profile_dir = self._chatgpt_local_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)

        session_id = f"local-chatgpt-{uuid4().hex[:8]}"
        timeout_seconds = int((self.settings.browser_checkout_cloud_timeout_minutes or 15) * 60)
        task = asyncio.create_task(self._run_local_chatgpt_sync_browser(profile_dir, timeout_seconds))
        self._local_sync_tasks[session_id] = task
        task.add_done_callback(lambda _done: self._local_sync_tasks.pop(session_id, None))

        return BrowserProfileSyncSession(
            store="ChatGPT",
            provider="local_browser",
            profile_id=str(profile_dir),
            session_id=session_id,
            live_url=CHATGPT_START_URL,
            login_url=CHATGPT_LOGIN_URL,
            timeout_at=datetime.now(timezone.utc),
            message=(
                "A local Chromium window should open on this machine. Sign into ChatGPT there, "
                "verify the Instacart app is available, then close the window and refresh status."
            ),
        )

    def _require_sdk(self) -> None:
        available, reason = browser_use_sdk_runtime_status()
        if not available:
            raise BrowserProfileSyncUnavailableError(reason or "Browser Use cloud profile sync is unavailable.")

    def _ensure_cloud_configuration(self, store: str) -> None:
        config = STORE_PROFILE_CONFIGS[store]
        if not self.settings.browser_checkout_use_cloud:
            raise BrowserProfileSyncUnavailableError(
                f"SHOPPER_BROWSER_CHECKOUT_USE_CLOUD must be true to use {config.display_name} profile sync."
            )
        if not self.settings.browser_use_api_key:
            raise BrowserProfileSyncUnavailableError(
                f"BROWSER_USE_API_KEY is required for {config.display_name} profile sync."
            )
        if not self.settings.browser_checkout_cloud_profile_id:
            raise BrowserProfileSyncUnavailableError(
                f"SHOPPER_BROWSER_CHECKOUT_CLOUD_PROFILE_ID is required for {config.display_name} profile sync."
            )

    @staticmethod
    def _sdk_request_options() -> dict[str, int]:
        return {
            "timeout_in_seconds": SDK_REQUEST_TIMEOUT_SECONDS,
            "max_retries": 1,
        }

    def _build_sdk_client(self):
        from browser_use_sdk import AsyncBrowserUse

        return AsyncBrowserUse(api_key=self.settings.browser_use_api_key)

    async def _create_browser_session_request(
        self,
        client,
        *,
        disable_proxy: bool = False,
        store: str | None = None,
    ):
        config = STORE_PROFILE_CONFIGS.get(store or "")
        proxy_country_code = None
        if not disable_proxy and (config is None or config.use_cloud_proxy):
            proxy_country_code = self.settings.browser_checkout_cloud_proxy_country_code or None

        return await client.browsers.create_browser_session(
            profile_id=self.settings.browser_checkout_cloud_profile_id,
            proxy_country_code=proxy_country_code,
            timeout=self.settings.browser_checkout_cloud_timeout_minutes or 15,
            request_options=self._sdk_request_options(),
        )

    async def _create_browser_session_without_proxy_retry(self, client, config: StoreProfileConfig):
        if not self.settings.browser_checkout_cloud_proxy_country_code:
            raise BrowserProfileSyncUnavailableError(
                "Browser Use timed out while creating the live session. Please try again."
            )

        logger.warning(
            "Browser Use timed out while opening %s sync session; retrying without proxy.",
            config.display_name,
        )
        try:
            return await self._create_browser_session_request(client, disable_proxy=True, store=config.key)
        except httpx.ReadTimeout as retry_exc:
            raise BrowserProfileSyncUnavailableError(
                "Browser Use timed out while creating the live session, even after retrying without proxy. Please try again."
            ) from retry_exc
        except Exception as retry_exc:
            raise BrowserProfileSyncUnavailableError(
                f"Could not create the {config.display_name} live session after retrying without proxy: {retry_exc}"
            ) from retry_exc

    async def _get_status(self, store: str) -> BrowserProfileSyncStatus:
        config = STORE_PROFILE_CONFIGS[store]
        available, reason = browser_use_sdk_runtime_status()
        if not available:
            return self._base_status(store, configured=False, ready=False, message=reason or "Browser Use SDK unavailable.")

        if not self.settings.browser_checkout_use_cloud:
            return self._base_status(
                store,
                configured=False,
                ready=False,
                message=(
                    f"Cloud checkout is disabled. Enable SHOPPER_BROWSER_CHECKOUT_USE_CLOUD to sync "
                    f"{config.display_name} login."
                ),
            )

        if not self.settings.browser_use_api_key or not self.settings.browser_checkout_cloud_profile_id:
            return self._base_status(
                store,
                configured=False,
                ready=False,
                message="Cloud checkout is missing a Browser Use API key or cloud profile id.",
            )

        client = self._build_sdk_client()
        try:
            profile = await client.profiles.get_profile(self.settings.browser_checkout_cloud_profile_id)
        except httpx.ReadTimeout:
            return self._base_status(
                store,
                configured=True,
                ready=False,
                message="Browser Use timed out while checking the cloud profile. Please try again.",
            )
        except Exception as exc:
            return self._base_status(
                store,
                configured=False,
                ready=False,
                message=f"Could not load the Browser Use cloud profile: {exc}",
            )

        cookie_domains = list(profile.cookie_domains or [])
        ready = any(config.cookie_domain_fragment in domain for domain in cookie_domains)
        return BrowserProfileSyncStatus(
            store=config.display_name,
            configured=True,
            ready=ready,
            profile_id=profile.id,
            profile_name=profile.name,
            login_url=config.login_url,
            start_url=config.start_url,
            cookie_domains=cookie_domains,
            last_used_at=profile.last_used_at,
            message=(
                f"{config.display_name} cookies were found in the Browser Use cloud profile."
                if ready
                else f"No {config.display_name} cookies were found yet. Open a live session and sign in once."
            ),
        )

    async def _create_sync_session(self, store: str) -> BrowserProfileSyncSession:
        self._require_sdk()
        self._ensure_cloud_configuration(store)
        config = STORE_PROFILE_CONFIGS[store]

        client = self._build_sdk_client()
        try:
            session = await self._create_browser_session_request(client, store=store)
        except httpx.ReadTimeout as exc:
            session = await self._create_browser_session_without_proxy_retry(client, config)
        except Exception as exc:
            if not is_cloud_session_limit_error(exc):
                raise BrowserProfileSyncUnavailableError(
                    f"Could not create the {config.display_name} live session: {exc}"
                ) from exc
            stopped = await stop_active_cloud_browser_sessions(self.settings)
            logger.warning(
                "Browser Use cloud session limit reached while opening %s sync session; stopped %s active sessions and retrying.",
                config.display_name,
                stopped,
            )
            try:
                session = await self._create_browser_session_request(client, store=store)
            except httpx.ReadTimeout as retry_exc:
                session = await self._create_browser_session_without_proxy_retry(client, config)
            except Exception as retry_exc:
                raise BrowserProfileSyncUnavailableError(
                    f"Could not create the {config.display_name} live session after retrying: {retry_exc}"
                ) from retry_exc
        if not session.live_url:
            raise BrowserProfileSyncUnavailableError("Browser Use did not return a live URL for the sync session.")

        return BrowserProfileSyncSession(
            store=config.display_name,
            profile_id=self.settings.browser_checkout_cloud_profile_id,
            session_id=session.id,
            live_url=session.live_url,
            login_url=config.login_url,
            timeout_at=session.timeout_at,
            message=(
                (
                    "Open the live session, sign into ChatGPT, and make sure the Instacart app is connected "
                    "before closing it."
                )
                if store == "chatgpt"
                else (
                    f"Open the live session, sign into {config.display_name}, choose your delivery store, "
                    "and confirm a saved payment method before closing it."
                )
            ),
        )

    async def get_walmart_status(self) -> BrowserProfileSyncStatus:
        return await self._get_status("walmart")

    async def create_walmart_sync_session(self) -> BrowserProfileSyncSession:
        return await self._create_sync_session("walmart")

    async def get_instacart_status(self) -> BrowserProfileSyncStatus:
        return await self._get_status("instacart")

    async def create_instacart_sync_session(self) -> BrowserProfileSyncSession:
        return await self._create_sync_session("instacart")

    async def get_chatgpt_status(self) -> BrowserProfileSyncStatus:
        return await self._get_chatgpt_status()

    async def create_chatgpt_sync_session(self) -> BrowserProfileSyncSession:
        return await self._create_chatgpt_local_sync_session()
