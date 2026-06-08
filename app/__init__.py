"""进程启动、依赖组装（非业务层）。"""

from app.bootstrap import configure, get_app_context
from app.context import AppContext

__all__ = ["AppContext", "configure", "get_app_context"]
