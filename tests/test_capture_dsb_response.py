import base64
import gzip
import json

from dsb_bot.capture_dsb_response import sanitize_envelope


def test_sanitized_fixture_keeps_protocol_shape_and_removes_sensitive_values():
    payload = {
        "Resultcode": 0,
        "ResultStatusInfo": "private account detail",
        "ResultMenuItems": [
            {
                "Title": "Inhalte",
                "SchoolId": "private-school-id",
                "Childs": [
                    {
                        "Title": "PlÃ¤ne",
                        "Root": {
                            "Childs": [
                                {
                                    "Title": "private schedule title",
                                    "Date": "2026-11-06",
                                    "Childs": [{"Detail": "https://private.invalid/secret.html"}],
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    }
    envelope = {
        "d": base64.b64encode(
            gzip.compress(json.dumps(payload).encode("utf-8"))
        ).decode("ascii")
    }

    sanitized = sanitize_envelope(envelope)
    decoded = json.loads(gzip.decompress(base64.b64decode(sanitized["d"])))
    menu = decoded["ResultMenuItems"][0]
    item = menu["Childs"][0]["Root"]["Childs"][0]

    assert decoded["Resultcode"] == 0
    assert menu["Title"] == "Inhalte"
    assert menu["SchoolId"] == "[REDACTED]"
    assert item["Title"] == "[REDACTED]"
    assert item["Date"] == "2026-11-06"
    assert item["Childs"][0]["Detail"] == "https://example.invalid/redacted.html"
    assert "private" not in json.dumps(decoded)
