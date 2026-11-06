import base64
import gzip
import json

import httpx
import pytest

from dsb_bot.dsb_client import DSBClient, DSBRequestError


def _encoded_response(payload):
    inner = gzip.compress(json.dumps(payload).encode("utf-8"))
    return {"d": base64.b64encode(inner).decode("ascii")}


def test_successful_empty_menu_is_distinct_from_failed_request():
    response_body = _encoded_response(
        {
            "Resultcode": 0,
            "ResultMenuItems": [
                {"Title": "Inhalte", "Childs": [{"Title": "Pläne", "Root": {"Childs": []}}]}
            ],
        }
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body)
    )
    client = DSBClient(
        "user", "password", client=httpx.Client(transport=transport)
    )

    assert client.fetch_menu_links() == []


def test_nonzero_result_code_raises_instead_of_returning_empty():
    response_body = _encoded_response(
        {"Resultcode": 17, "ResultStatusInfo": "denied", "ResultMenuItems": []}
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body)
    )
    client = DSBClient(
        "user", "password", client=httpx.Client(transport=transport)
    )

    with pytest.raises(DSBRequestError, match="Resultcode"):
        client.fetch_menu_links()


def test_successful_menu_extracts_html_schedule_links():
    response_body = _encoded_response(
        {
            "Resultcode": 0,
            "ResultMenuItems": [
                {
                    "Title": "Inhalte",
                    "Childs": [
                        {
                            "Title": "Pläne",
                            "Root": {
                                "Childs": [
                                    {
                                        "Date": "2026-11-06",
                                        "Title": "Schüler heute",
                                        "Childs": [
                                            {
                                                "Detail": "https://example.invalid/plan.html"
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                }
            ],
        }
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body)
    )
    client = DSBClient(
        "user", "password", client=httpx.Client(transport=transport)
    )

    assert client.fetch_menu_links() == [
        {
            "detail": "https://example.invalid/plan.html",
            "date": "2026-11-06",
            "title": "Schüler heute",
        }
    ]
