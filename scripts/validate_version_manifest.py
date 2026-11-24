"""校验 Agent 版本清单（本地门禁之一，对应讲义 §8.8）。"""

from pathlib import Path

from release_guard.manifest import validate_manifest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "release" / "agent_versions.json"


def main() -> None:
    problems = validate_manifest(PROJECT_ROOT, MANIFEST)
    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)
    print("版本清单校验通过")


if __name__ == "__main__":
    main()