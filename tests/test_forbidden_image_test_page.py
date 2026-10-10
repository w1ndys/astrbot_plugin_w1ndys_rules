# 图片检测测试页：请求体只交这张图，结论只认本机解码。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class ForbiddenImageTestPageSourceTest(unittest.TestCase):
    """验证新 Tab、上传限制和请求字段。"""

    def test_tab_in_nav_source(self) -> None:
        """新 Tab 挨着违禁测试，还是页内面板。"""
        nav = (SRC / "nav.ts").read_text()
        self.assertIn('key: "forbidden-image-test", label: "图片检测测试"', nav)

    def test_upload_accepts_four_types_and_8mb(self) -> None:
        """只收 png、jpeg、webp、gif，且不超过 8MB；不合规在本地就拦住。"""
        js = (SRC / "forbidden-image-test-view.tsx").read_text()
        self.assertIn("8388608", js)
        self.assertIn("image/png", js)
        self.assertIn("image/jpeg", js)
        self.assertIn("image/webp", js)
        self.assertIn("image/gif", js)
        self.assertIn("beforeUpload", js)

    def test_request_body_has_no_qr_found(self) -> None:
        """只提交图片字节；旧页的二维码开关不发给新接口。"""
        js = (SRC / "forbidden-image-test-view.tsx").read_text()
        self.assertIn("forbidden/image-test", js)
        self.assertIn("image_base64", js)
        self.assertNotIn("qr_found", js)

    def test_engine_state_not_shown_as_no_code(self) -> None:
        """预检没过显示本次未检测；引擎没加载显示固定未识别文案。"""
        js = (SRC / "forbidden-image-test-view.tsx").read_text()
        self.assertIn("本次未检测", js)
        self.assertIn("二维码引擎未加载，本次未识别", js)

    def test_qr_area_shows_hit_layer_and_layer_states(self) -> None:
        """二维码区报命中层和三个分层状态；本次没走到的层显示本次未加载。"""
        js = (SRC / "forbidden-image-test-view.tsx").read_text()
        self.assertIn("命中层", js)
        self.assertIn("本次未加载", js)
        # 标签改名：后端这个字段已经按命中层计数，不再是 QReader 的框数
        self.assertIn("检出数量", js)
        self.assertNotIn("框数量", js)


class ForbiddenImageTestPageAssetTest(unittest.TestCase):
    """构建产物要和源码一致。"""

    def test_bundle_contains_new_tab(self) -> None:
        """pages/console 是构建后的单文件，重跑 npm run build 才会带上新 Tab。"""
        bundle = (PAGE / "assets" / "index.js").read_text()
        self.assertIn("图片检测测试", bundle)

    def test_bundle_contains_qr_labels(self) -> None:
        """构建产物也要带新的二维码标签，否则页面还停在旧「框数量」。"""
        bundle = (PAGE / "assets" / "index.js").read_text()
        self.assertIn("命中层", bundle)
        self.assertIn("检出数量", bundle)
