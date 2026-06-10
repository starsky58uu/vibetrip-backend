"""Alembic revision 鏈完整性（不需真實 DB）。"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_migration_head() -> None:
    root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "002_personal_spot"


def test_revision_chain_is_linear() -> None:
    root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))
    revisions = list(script.walk_revisions())
    ids = {r.revision for r in revisions}
    assert "001_initial" in ids
    assert "002_personal_spot" in ids
    assert len(revisions) == 2
