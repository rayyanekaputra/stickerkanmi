import pytest

from stickerkanmi.units import mm_to_px, parse_length, parse_size


def test_parse_length_units():
    assert parse_length("2.5") == 2.5
    assert parse_length("2.5mm") == 2.5
    assert parse_length("1cm") == 10
    assert parse_length("1in") == pytest.approx(25.4)
    assert parse_length('0.5"') == pytest.approx(12.7)
    assert parse_length("2", "in") == pytest.approx(50.8)


def test_parse_length_rejects_junk():
    with pytest.raises(ValueError):
        parse_length("abc")


def test_parse_size():
    assert parse_size("50mm") == (50, 50)
    assert parse_size("60x40") == (60, 40)
    w, h = parse_size("2x1in")
    assert (w, h) == (pytest.approx(50.8), pytest.approx(25.4))


def test_mm_to_px():
    assert mm_to_px(25.4, 300) == pytest.approx(300)
