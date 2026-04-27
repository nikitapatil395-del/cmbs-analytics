"""Runtime configuration for the CMBS analytics tool."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - python-dotenv is optional
    pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
SAMPLE_DATA_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model: str
    prospectus_path: Path | None
    sample_data_dir: Path

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("CMBS_MODEL", "claude-sonnet-4-5")
    pros_override = os.getenv("CMBS_PROSPECTUS_PATH")
    prospectus = Path(pros_override) if pros_override else None
    return Settings(
        anthropic_api_key=key,
        model=model,
        prospectus_path=prospectus,
        sample_data_dir=SAMPLE_DATA_DIR,
    )


SETTINGS = load_settings()


# Paths for the synthetic dataset written by cmbs.mock_data
MOCK_LOAN_TAPE = SAMPLE_DATA_DIR / "loan_tape.csv"
MOCK_CASHFLOW_LOG = SAMPLE_DATA_DIR / "waterfall.log"
MOCK_BOND_STRUCTURE = SAMPLE_DATA_DIR / "bonds.csv"
MOCK_REMITTANCE = SAMPLE_DATA_DIR / "remittance.csv"
MOCK_PROSPECTUS = SAMPLE_DATA_DIR / "prospectus.pdf"
MOCK_DEAL_META = SAMPLE_DATA_DIR / "deal.json"
