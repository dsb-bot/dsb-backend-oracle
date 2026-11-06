import logging

import httpx


logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(
        self,
        warning_webhook: str | None,
        plans_webhook: str | None,
        ping_role_id: str | None = None,
        *,
        client: httpx.Client | None = None,
    ):
        self.warning_webhook = warning_webhook
        self.plans_webhook = plans_webhook
        self.ping_role_id = ping_role_id
        self._client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def send_warning(self, message: str) -> bool:
        if not self.warning_webhook:
            return False
        content = message
        payload: dict[str, object] = {
            "username": "DSB-Monitor",
            "content": content,
        }
        if self.ping_role_id:
            payload["content"] = f"<@&{self.ping_role_id}> {message}"
            payload["allowed_mentions"] = {
                "parse": [],
                "roles": [self.ping_role_id],
            }
        return self._post(self.warning_webhook, payload, "warning")

    def send_plan_update(self, plans: list[tuple[str, str]]) -> bool:
        if not self.plans_webhook or not plans:
            return False
        fields = [
            {"name": title, "value": f"Datum: {target_date}", "inline": False}
            for target_date, title in plans
        ]
        payload = {
            "username": "DSB-Bot",
            "avatar_url": "https://www.dsbmobile.de/img/logo_dsbmobile.png",
            "content": "Vertretungspläne wurden aktualisiert.",
            "embeds": [
                {
                    "title": "Aktuelle Vertretungspläne",
                    "color": 0x1ABC9C,
                    "fields": fields,
                }
            ],
        }
        return self._post(self.plans_webhook, payload, "plan update")

    def _post(self, url: str, payload: dict[str, object], event: str) -> bool:
        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Discord %s notification failed", event)
            return False
        return True
