"""Asynchronous Python client for Clever EV charger subscription and EV charger at home"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import async_timeout
from aiohttp.client import ClientSession
from aiohttp.hdrs import METH_GET, METH_POST
from yarl import URL

from .exceptions import CleverError, CleverConnectionError
from .models import (
    SendEmail,
    VerifyLink,
    ObtainUserSecret,
    ObtainApiToken,
    UserInfo,
    Transactions,
    ModTransactions,
    EvseInfo,
    Energitillaeg,
)
from .const import AUTHORIZATION_HEADER, LOGGER
from .urls import (
    SEND_AUTH_EMAIL,
    VERIFY_LINK,
    OBTAIN_USER_SECRET,
    OBTAIN_API_TOKEN,
    GET_USER_INFO,
    GET_TRANSACTIONS,
    GET_EVSE_INFO,
    GET_ENERGITILLAEG,
)


@dataclass
class Clever:
    """Class for handling connection with Clever backend"""

    request_timeout: int = 10
    session: ClientSession | None = None
    _close_session: bool = False

    async def _request(
        self,
        url: str,
        method: str = METH_GET,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle request to Clever backend"""

        headers = {"authorization": AUTHORIZATION_HEADER}
        LOGGER.debug(f"Request URL: {url}")
        LOGGER.debug(f"Request headers: {headers}")
        if data:
            LOGGER.debug(f"Request data: {data}")

        if self.session is None:
            self.session = ClientSession()
            self._close_session = True

        try:
            async with async_timeout.timeout(self.request_timeout):
                response = await self.session.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                )
                response.raise_for_status()
                LOGGER.debug(f"Response status: {response.status}")
                response_json = await response.json()
                LOGGER.debug(f"Response JSON: {response_json}")
                return response_json
        except asyncio.TimeoutError as exception:
            msg = "Timeout while connecting to Clever backend"
            LOGGER.error(msg)
            raise CleverConnectionError(msg) from exception
        except Exception as exception:
            LOGGER.error(f"Request failed: {exception}")
            raise

    async def close(self) -> None:
        """Close client session."""

        if self.session and self._close_session:
            await self.session.close()

    async def __aenter__(self) -> Clever:
        """Async enter."""
        return self

    async def __aexit__(self, *_exc_inf: Any) -> None:
        """Async exit."""
        await self.close()


class Auth(Clever):
    """Handles Clever API auth process"""

    async def send_auth_email(self, email: str) -> SendEmail:
        """Request a verify login email from Clever"""
        url = f"{SEND_AUTH_EMAIL}?email={email}"
        resp = await self._request(url)
        return SendEmail.parse_obj(resp)

    async def verify_link(self, auth_link: str, email: str) -> VerifyLink:
        """Obtain secretCode sent to email."""
        secret_code = URL(auth_link).query["secretCode"]
        url = f"{VERIFY_LINK}?token={secret_code}&email={email}"
        resp = await self._request(url)
        resp["secret_code"] = secret_code
        model = VerifyLink.parse_obj(resp)
        if model.data["result"] != "Verified":
            msg = model.data["result"]
            raise CleverError(msg)
        return model

    async def obtain_user_secret(
        self, email: str, first_name: str, last_name: str, secret_code: str
    ) -> ObtainUserSecret:
        """Exchange secret_code for user_secret."""
        url = OBTAIN_USER_SECRET
        payload = {
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "token": secret_code,
        }
        resp = await self._request(url, method=METH_POST, data=payload)
        model = ObtainUserSecret.parse_obj(resp)
        if model.data["userSecret"] == "null":
            msg = model.data["verificationResponse"]["result"]
            raise CleverError(msg)
        return model

    async def obtain_api_token(self, user_secret: str, email: str):
        """Exchange user_secret for api_token."""
        url = f"{OBTAIN_API_TOKEN}?secret={user_secret}&email={email}"
        resp = await self._request(url)
        model = ObtainApiToken.parse_obj(resp)
        if model.data is None:
            msg = model.status_message
            raise CleverError(msg)
        return model


@dataclass
class Subscription(Clever):
    """Dataclass representing a Clever subscription."""

    api_token: str = None

    async def get_user_info(self) -> UserInfo:
        """Get info of user"""
        url = GET_USER_INFO.format(api_token=self.api_token)
        resp = await self._request(url)
        model = UserInfo.parse_obj(resp)
        return model

    async def get_transactions(self, box_id=None) -> Transactions:
        """Get charging transactions"""
        url = GET_TRANSACTIONS.format(api_token=self.api_token)
        resp = await self._request(url)
        model = Transactions.parse_obj(resp)
        return model

    async def get_evse_info(self) -> EvseInfo:
        """Get info about EVSE"""
        url = GET_EVSE_INFO.format(api_token=self.api_token)
        resp = await self._request(url)
        model = EvseInfo.parse_obj(resp)
        return model

    async def get_energitillaeg(self) -> Energitillaeg:
        """Get energitillaeg."""
        url = GET_ENERGITILLAEG.format(api_token=self.api_token)
        resp = await self._request(url)
        model = Energitillaeg.parse_obj(resp)
        return model
