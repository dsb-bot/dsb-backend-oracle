import base64
import gzip
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx

from dsb_bot.models import FetchedDocument


DSB_DATA_URL = "https://app.dsbcontrol.de/JsonHandler.ashx/GetData"


class DSBRequestError(RuntimeError):
    pass


class DSBClient:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        client: httpx.Client | None = None,
        data_url: str = DSB_DATA_URL,
    ):
        self.username = username
        self.password = password
        self.data_url = data_url
        self._client = client or httpx.Client(timeout=15)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_schedules(self) -> list[FetchedDocument]:
        links = self.fetch_menu_links()
        documents: list[FetchedDocument] = []
        for link in links:
            try:
                response = self._client.get(link["detail"], timeout=15)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise DSBRequestError("Could not retrieve a DSB schedule document") from exc
            content_type = response.headers.get("content-type", "text/html")
            if not content_type.lower().startswith("text/html"):
                raise DSBRequestError(
                    "DSB schedule response was not served as HTML"
                )
            documents.append(
                FetchedDocument(
                    title=link["title"],
                    detail_url=link["detail"],
                    body=response.content,
                    content_type=content_type,
                )
            )
        return documents

    def fetch_menu_links(self) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        request_data = {
            "UserId": self.username,
            "UserPw": self.password,
            "AppVersion": "2.5.9",
            "Language": "de",
            "OsVersion": "28 8.0",
            "AppId": str(uuid.uuid4()),
            "Device": "SM-G30F",
            "BundleId": "de.heinekingmedia.dsbmobile",
            "Date": now,
            "LastUpdate": now,
        }
        compressed = base64.b64encode(
            gzip.compress(
                json.dumps(request_data, separators=(",", ":")).encode("utf-8")
            )
        ).decode("ascii")
        try:
            response = self._client.post(
                self.data_url,
                json={"req": {"Data": compressed, "DataType": 1}},
                timeout=15,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DSBRequestError("DSB menu request failed") from exc

        try:
            envelope = response.json()
            if not isinstance(envelope, dict):
                raise DSBRequestError("DSB menu response envelope is not an object")
            encoded_data = envelope["d"]
            payload = json.loads(gzip.decompress(base64.b64decode(encoded_data)))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise DSBRequestError("DSB menu response could not be decoded") from exc

        if not isinstance(payload, dict):
            raise DSBRequestError("Decoded DSB menu response is not an object")
        result_code = payload.get("Resultcode")
        if result_code != 0:
            raise DSBRequestError(f"DSB returned Resultcode {result_code!r}")

        menu_items = payload.get("ResultMenuItems")
        if not isinstance(menu_items, list):
            raise DSBRequestError("DSB menu response has no ResultMenuItems list")
        contents = next(
            (
                item
                for item in menu_items
                if isinstance(item, dict) and item.get("Title") == "Inhalte"
            ),
            None,
        )
        if contents is None:
            raise DSBRequestError("DSB menu response has no 'Inhalte' entry")
        children = contents.get("Childs")
        if not isinstance(children, list):
            raise DSBRequestError("DSB 'Inhalte' entry has no Childs list")
        plans = next(
            (
                child
                for child in children
                if isinstance(child, dict) and child.get("Title") == "Pläne"
            ),
            None,
        )
        if plans is None:
            raise DSBRequestError("DSB menu response has no 'Pläne' entry")
        root = plans.get("Root")
        root_children = root.get("Childs") if isinstance(root, dict) else None
        if not isinstance(root_children, list):
            raise DSBRequestError("DSB 'Pläne' entry has no Root.Childs list")

        links: list[dict[str, str]] = []
        for item in root_children:
            if not isinstance(item, dict):
                continue
            nested = item.get("Childs")
            if not isinstance(nested, list) or not nested or not isinstance(nested[0], dict):
                continue
            detail = nested[0].get("Detail")
            if not isinstance(detail, str):
                continue
            absolute_detail = urljoin(self.data_url, detail)
            parsed_detail = urlsplit(absolute_detail)
            path = parsed_detail.path.lower()
            if not path.endswith((".htm", ".html")):
                continue
            if parsed_detail.scheme not in {"http", "https"} or not parsed_detail.netloc:
                raise DSBRequestError("DSB schedule link is not a valid HTTP(S) URL")
            links.append(
                {
                    "detail": absolute_detail,
                    "date": str(item.get("Date") or ""),
                    "title": str(item.get("Title") or ""),
                }
            )
        return links
