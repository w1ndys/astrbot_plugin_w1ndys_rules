# 本群最后发言：没记录不当活跃，写过再查，超 7 天失效，重开库仍在。

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules._shared.db import connect
from astrbot_plugin_w1ndys_rules.business.activity import (
    is_recently_active,
    record_speak,
)
from astrbot_plugin_w1ndys_rules.data.activity_store import ActivityStore


class ActivityStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = ActivityStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_not_active(self) -> None:
        self.assertFalse(self.store.is_within_window("123", "10001"))
        self.assertFalse(is_recently_active(self.store, "123", "10001"))

    def test_empty_ids_are_not_active(self) -> None:
        self.assertFalse(is_recently_active(self.store, "", "10001"))
        self.assertFalse(is_recently_active(self.store, "123", ""))

    async def test_touch_then_active(self) -> None:
        await self.store.touch("123", "10001")
        self.assertTrue(self.store.is_within_window("123", "10001"))
        self.assertTrue(is_recently_active(self.store, "123", "10001"))

    async def test_groups_are_isolated(self) -> None:
        await self.store.touch("111", "10001")
        self.assertTrue(self.store.is_within_window("111", "10001"))
        self.assertFalse(self.store.is_within_window("222", "10001"))

    async def test_users_are_isolated(self) -> None:
        await self.store.touch("123", "10001")
        self.assertFalse(self.store.is_within_window("123", "10002"))

    async def test_eighth_day_is_not_active(self) -> None:
        await self.store.touch("123", "10001")
        _set_last_seen(
            self.db_path,
            "123",
            "10001",
            datetime.now() - timedelta(days=8),
        )
        reopened = ActivityStore(self.db_path)
        self.assertFalse(reopened.is_within_window("123", "10001"))
        self.assertFalse(is_recently_active(reopened, "123", "10001"))

    async def test_survives_reopen(self) -> None:
        await record_speak(self.store, "123", "10001")
        reopened = ActivityStore(self.db_path)
        self.assertTrue(reopened.is_within_window("123", "10001"))

    async def test_record_speak_skips_empty(self) -> None:
        await record_speak(self.store, "", "10001")
        await record_speak(self.store, "123", "")
        self.assertFalse(self.store.is_within_window("123", "10001"))
        self.assertFalse(self.store.is_within_window("", "10001"))


def _set_last_seen(db_path: Path, group_id: str, user_id: str, when: datetime) -> None:
    """测试里把上次发言改成指定时间，再靠重开库读快照。"""
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE last_speak SET last_seen = ? WHERE group_id = ? AND user_id = ?",
            (stamp, group_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()
