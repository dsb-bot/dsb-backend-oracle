import httpx

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
