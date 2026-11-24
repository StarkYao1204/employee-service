"""记录最小化安全审计事件，不写入密码、Token 或敏感 Prompt。"""

# 安全审计：谁做了什么，记一行
import json
import logging
from datetime import UTC, datetime

audit_logger = logging.getLogger("security_audit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s security_audit %(message)s"))
    audit_logger.addHandler(handler)
audit_logger.propagate = False


def audit_event(
    action: str,
    result: str,
    *,
    user_id: str | None = None,
    resource: str | None = None,
    reason: str | None = None,
) -> None:
    """用固定字段记录谁对什么做了什么，以及结果如何。"""

    event = {
        "occurred_at": datetime.now(UTC).isoformat(),
        "action": action,
        "result": result,
        "user_id": user_id,
        "resource": resource,
        "reason": reason,
    }
    audit_logger.info(json.dumps(event, ensure_ascii=False))
