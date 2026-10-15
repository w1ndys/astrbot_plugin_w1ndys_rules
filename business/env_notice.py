# 业务层：视觉依赖体检。加载时查一遍库能不能导入，缺的写成给管理员的私聊文案。
# 只判断「有没有」，不构造引擎、不加载模型，也不写库。

import importlib.util

from ..entity.constants import VISUAL_INSTALL_COMMANDS, VISUAL_PACKAGES


def missing_packages(finder=None) -> list:
    """缺哪些视觉依赖。返回 (import 名, pip 包名) 列表，顺序照 VISUAL_PACKAGES。"""
    find = finder or importlib.util.find_spec
    missing = []
    for module_name, pip_name in VISUAL_PACKAGES:
        try:
            found = find(module_name)
        except Exception:  # noqa: BLE001 - 父包导入失败也算没装，体检不能中断
            # 拿不到模块就当没装
            found = None
        # 找不到就记下来，交给文案
        if found is None:
            missing.append((module_name, pip_name))
    return missing


def notice_text(missing: list) -> str:
    """缺依赖时给管理员的私聊：缺什么、怎么补、补完要重启。"""
    lines = ["[群管] 视觉环境不完整，二维码识别和图片转写会退化："]
    for module_name, pip_name in missing:
        lines.append(f"- 缺 {module_name}（pip 包 {pip_name}）")
    lines.append("在 astrbot 容器里补装（国内镜像）：")
    for command in VISUAL_INSTALL_COMMANDS:
        lines.append(command)
    lines.append("装完 docker restart astrbot。")
    return "\n".join(lines)
