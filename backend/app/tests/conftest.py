import os
import tempfile

# 必须在导入 app 之前指向临时数据库
_tmp = tempfile.mkdtemp(prefix="wishclaim-test-")
os.environ.setdefault("DATA_DIR", _tmp)

from app import seed  # noqa: E402

# TestClient 不保证触发 startup 事件，显式建表+种子
seed.init_db()
