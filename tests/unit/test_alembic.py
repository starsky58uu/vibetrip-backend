"""Alembic revision 鏈完整性（不需 import alembic 套件，避免與 alembic/ 目錄同名衝突）。"""

import re
from pathlib import Path


def _parse_revisions() -> dict[str, str | None]:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    revisions: dict[str, str | None] = {}
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev_match = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down_match = re.search(r'^down_revision:\s*[^=]*=\s*(?:"([^"]+)"|None)', text, re.M)
        assert rev_match, f"缺少 revision: {path.name}"
        revisions[rev_match.group(1)] = down_match.group(1) if down_match else None
    return revisions


def test_single_migration_head() -> None:
    revisions = _parse_revisions()
    # 沒有被任何 revision 指為 down_revision 的就是 head
    all_downs = {d for d in revisions.values() if d}
    heads = [r for r in revisions if r not in all_downs]
    assert len(heads) == 1
    assert heads[0] == "002_personal_spot"


def test_revision_chain_is_linear() -> None:
    revisions = _parse_revisions()
    assert revisions.get("001_initial") is None
    assert revisions.get("002_personal_spot") == "001_initial"
    assert len(revisions) == 2
