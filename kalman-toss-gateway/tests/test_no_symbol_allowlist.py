from __future__ import annotations

import unittest
from pathlib import Path


class NoSymbolAllowlistReferencesTests(unittest.TestCase):
    def test_runtime_has_no_symbol_allowlist_references(self) -> None:
        root = Path(__file__).resolve().parents[1]
        targets = [
            root / "app",
            root / "engine",
            root / "scripts",
            root / ".env.example",
            root / "README.md",
        ]

        forbidden = [
            "ALLOW_" + "SYMBOLS",
            "allowed" + "Symbols",
            "allowed_" + "symbols",
            "symbol_" + "allowed",
            "SYMBOL_" + "NOT_ALLOWED",
            "SYMBOL_" + "LIMIT_EXCEEDED",
            "DEFAULT_" + "SYMBOL_LIMIT_KRW",
            "QQQ_" + "LIMIT_KRW",
            "NVDA_" + "LIMIT_KRW",
            "IONQ_" + "LIMIT_KRW",
        ]

        hits: list[str] = []

        for target in targets:
            files = target.rglob("*") if target.is_dir() else [target]
            for path in files:
                if not path.is_file():
                    continue
                if path.suffix in {".pyc", ".b64"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for token in forbidden:
                    if token in text:
                        hits.append(f"{path.relative_to(root)}: {token}")

        self.assertEqual(hits, [], "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
