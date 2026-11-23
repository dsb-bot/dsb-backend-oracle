import httpx
import logging

from dsb_bot.discord_notifier import DiscordNotifier


def test_warning_preserves_explicit_role_ping_and_plan_update_is_sent():
    payloads = []

    def handle(request):
        payloads.append(request.read())
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    notifier = DiscordNotifier(
        "https://discord.invalid/warn",
        "https://discord.invalid/plans",
        "123456",
        client=client,
    )

    assert notifier.send_warning("Sync failed")
    assert notifier.send_plan_update([("2026-11-06", "6.11.2026 Freitag")])
    assert len(payloads) == 2
    assert b"<@&123456>" in payloads[0]
    assert b"2026-11-06" in payloads[1]


def test_failed_webhook_does_not_log_secret_url(caplog):
    secret = "webhook-secret-token"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, request=request)
    )
    client = httpx.Client(transport=transport)
    notifier = DiscordNotifier(
        f"https://discord.invalid/api/webhooks/{secret}",
        None,
        client=client,
    )

    with caplog.at_level(logging.WARNING, logger="dsb_bot.discord_notifier"):
        assert not notifier.send_warning("Sync failed")

    assert "Discord warning notification failed" in caplog.text
    assert secret not in caplog.text
