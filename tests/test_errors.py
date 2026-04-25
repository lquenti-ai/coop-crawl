import pytest

from coopcrawl.errors import FiveXXError, FourXXError, classify_status


@pytest.mark.parametrize("code", [200, 201, 204, 301, 302, 304])
def test_2xx_3xx_pass(code: int) -> None:
    assert classify_status(code) is None


@pytest.mark.parametrize("code", [400, 401, 403, 404, 408, 410, 429])
def test_4xx_class(code: int) -> None:
    assert classify_status(code) is FourXXError


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_5xx_class(code: int) -> None:
    assert classify_status(code) is FiveXXError


def test_unexpected_falls_back_to_5xx() -> None:
    assert classify_status(999) is FiveXXError
