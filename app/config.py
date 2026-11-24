"""集中管理项目根目录路径与 .env 加载。"""

from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级）；knowledge/、static/、runtime/ 等数据目录都锚定在这里。
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)
