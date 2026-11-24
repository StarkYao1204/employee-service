"""Agent 版本清单校验：结构、路径边界与内容摘要。"""

import hashlib
import json
from pathlib import Path


class ManifestValidationError(Exception):
    """清单结构或证据校验失败。"""


def sha256(path: Path) -> str:
    """分块读取文件，避免大文件一次性进入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        # 每次读取 64 KiB；读到 b"" 时 iter 自动结束。
        for block in iter(lambda: file.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_file(root: Path, relative: str, expected: str | None) -> list[str]:
    problems: list[str] = []
    candidate = (root / relative).resolve()

    # 清单来自仓库，也不能盲目信任其中的相对路径。
    if not candidate.is_relative_to(root):
        return [f"路径越过项目根目录：{relative}"]
    if not candidate.is_file():
        return [f"清单文件不存在：{relative}"]
    if expected is not None and sha256(candidate) != expected:
        problems.append(f"摘要不一致：{relative}")
    return problems


def validate_manifest(root: Path, manifest_path: Path) -> list[str]:
    """返回问题列表；空列表代表清单通过校验。"""

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON 无法解析：{exc}"]

    problems: list[str] = []
    for key in ("service", "runtime", "agent", "knowledge"):
        if key not in data:
            problems.append(f"缺少顶层字段：{key}")

    for group, components in (
        ("agent", data.get("agent", {})),
        ("knowledge", data.get("knowledge", {})),
    ):
        for name, item in components.items():
            if not isinstance(item, dict) or "path" not in item:
                continue
            problems += [
                f"[{group}.{name}] {line}"
                for line in _check_file(root, item["path"], item.get("sha256"))
            ]
    return problems