# 视觉依赖体检：缺哪个报哪个，文案带补装命令。不加载真实引擎。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.env_notice import missing_packages, notice_text
from astrbot_plugin_w1ndys_rules.entity.constants import (
    VISUAL_INSTALL_COMMANDS,
    VISUAL_PACKAGES,
)


class MissingPackagesTest(unittest.TestCase):
    # 体检结果：装齐、缺几个、查找器抛错

    def test_all_installed_is_empty(self) -> None:
        # 都装好就没有可报的
        self.assertEqual(missing_packages(finder=lambda _name: object()), [])

    def test_reports_missing_pairs(self) -> None:
        # 缺 qreader 和微信层：按 VISUAL_PACKAGES 顺序报，带上 pip 包名
        def finder(name):
            # 这两个没装，其余正常
            if name in ("qreader", "cv2.wechat_qrcode"):
                return None
            return object()

        self.assertEqual(
            missing_packages(finder=finder),
            [("qreader", "qreader"), ("cv2.wechat_qrcode", "opencv-contrib-python")],
        )

    def test_finder_error_counts_as_missing(self) -> None:
        # 父包导入就抛错也算没装，不能让体检中断
        def finder(_name):
            raise ImportError("bad parent")

        self.assertEqual(len(missing_packages(finder=finder)), len(VISUAL_PACKAGES))


class NoticeTextTest(unittest.TestCase):
    # 私聊文案

    def test_lists_module_and_pip_name(self) -> None:
        # 缺什么要写成 import 名加 pip 包名，管理员才知道装哪个
        text = notice_text([("cv2.wechat_qrcode", "opencv-contrib-python")])
        self.assertIn("cv2.wechat_qrcode", text)
        self.assertIn("opencv-contrib-python", text)

    def test_carries_install_commands(self) -> None:
        # 两条补装命令都要在文案里，省得管理员自己查
        text = notice_text([("qreader", "qreader")])
        for command in VISUAL_INSTALL_COMMANDS:
            self.assertIn(command, text)
