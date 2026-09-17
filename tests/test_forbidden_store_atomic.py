# SQLite 多实例下的违禁配置修改测试。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.entity.constants import FORBIDDEN_KIND_TRIGGER


class ForbiddenStoreAtomicUpdateTest(unittest.IsolatedAsyncioTestCase):
    """验证多个 Store 实例修改同一个 SQLite 时以数据库状态为准。"""

    def setUp(self) -> None:
        """每个测试使用独立临时数据库。"""
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"

    def tearDown(self) -> None:
        """删除临时数据库。"""
        self._tmp.cleanup()

    async def test_second_instance_sees_first_update_as_missing(self) -> None:
        """第一个实例修改后，第二个实例不能基于旧快照再次修改旧值。"""
        first = ForbiddenStore(self.db_path)
        second = ForbiddenStore(self.db_path)
        await first.add("100", FORBIDDEN_KIND_TRIGGER, "广告")

        self.assertEqual(
            await first.update("100", FORBIDDEN_KIND_TRIGGER, "广告", "推广"),
            "updated",
        )
        self.assertEqual(
            await second.update("100", FORBIDDEN_KIND_TRIGGER, "广告", "引流"),
            "missing",
        )
        self.assertEqual(
            ForbiddenStore(self.db_path).list_contents("100", FORBIDDEN_KIND_TRIGGER),
            ["推广"],
        )
