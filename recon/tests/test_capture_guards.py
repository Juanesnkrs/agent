"""Guards for navigation clicks in the read-only capture tool."""

import pytest

from recon.capture import find_clickable, is_legal_link


class FakeElement:
    def __init__(self, text: str, href: str = "") -> None:
        self.text = text
        self.href = href

    def is_visible(self) -> bool:
        return True

    def inner_text(self, timeout: int | None = None) -> str:
        return self.text

    def get_attribute(self, name: str) -> str | None:
        return self.href if name == "href" else None


class FakeLocator:
    def __init__(self, elements: list[FakeElement]) -> None:
        self.elements = elements

    def count(self) -> int:
        return len(self.elements)

    def nth(self, index: int) -> FakeElement:
        return self.elements[index]


class FakePage:
    def __init__(self, elements: list[FakeElement]) -> None:
        self.elements = elements

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.elements if selector == "a" else [])


@pytest.mark.parametrize(
    ("text", "href"),
    [
        ("Términos y Condiciones de Apuestas Deportivas", "/?page=eula&tos=SPORTS"),
        ("Ayuda", "/ayuda"),
        ("Política de Privacidad", "/privacy"),
        ("Juego responsable", "/responsible-gaming"),
        ("Soporte", "/support"),
        ("Reglamento de apuestas", "/reglas-juegos/apuestas-deportivas"),
        ("Contacto", "/contact"),
        ("Cualquier texto", "/legal/terms"),
    ],
)
def test_legal_help_and_support_links_are_rejected(text: str, href: str) -> None:
    assert is_legal_link(text, href)


@pytest.mark.parametrize(
    ("text", "href"),
    [
        ("Deportes", "/?page=sportsbook"),
        ("Sportsbook", "/es/sports"),
        ("Baloncesto", "/apuestas-deportivas/baloncesto"),
        ("NBA", "#filter/basketball/nba"),
    ],
)
def test_sportsbook_links_are_not_rejected(text: str, href: str) -> None:
    assert not is_legal_link(text, href)


def test_find_clickable_skips_terms_and_returns_sportsbook() -> None:
    page = FakePage(
        [
            FakeElement("Términos y Condiciones", "/?page=eula&tos=TOC"),
            FakeElement("Deportes", "/?page=sportsbook"),
        ]
    )
    element, text = find_clickable(page, r"deportes|t[eé]rminos")
    assert element is not None
    assert text == "Deportes"
