"""Runtime system configuration helpers."""

from __future__ import annotations

from core.constants import AUTO_MODE_KEY, VALID_AUTO_MODES
from core.settings import Settings
from memory.store import MemoryStore


class SystemConfigService:
    """Read and mutate runtime flags backed by DB plus env override."""

    def __init__(self, store: MemoryStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def get_auto_mode(self) -> str:
        """Get AUTO_MODE using FORCE_AUTO_MODE override if set."""

        if self.settings.force_auto_mode and self.settings.force_auto_mode in VALID_AUTO_MODES:
            return self.settings.force_auto_mode

        mode = self.store.get_system_config(AUTO_MODE_KEY)
        if mode in VALID_AUTO_MODES:
            return mode
        return "DRY_RUN"

    def set_auto_mode(self, mode: str, updated_by: str) -> str:
        """Persist AUTO_MODE if valid and return stored mode."""

        if mode not in VALID_AUTO_MODES:
            raise ValueError(f"invalid mode: {mode}")
        self.store.set_system_config(AUTO_MODE_KEY, mode, updated_by)
        return mode
