"""Provider interface."""

from abc import ABC, abstractmethod

from surebets.models import OddsQuote


class OddsProvider(ABC):
    @abstractmethod
    def fetch_odds(self) -> list[OddsQuote]:
        """Return the current prematch odds quotes."""

