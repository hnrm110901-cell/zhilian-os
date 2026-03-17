"""诊断适配器加载问题"""
import sys
import os

sys.path.insert(0, "/app")

# 1. 检查路径
src = "/app/packages/api-adapters/pinzhi/src"
print("1. 路径:", src, "存在:", os.path.isdir(src))
print("   文件:", os.listdir(src))

# 2. 检查依赖
deps = ["httpx", "hashlib", "json", "time"]
for d in deps:
    try:
        __import__(d)
        print(f"2. {d}: OK")
    except ImportError as e:
        print(f"2. {d}: MISSING - {e}")

# 3. 尝试加载
try:
    from src.api.pos_sync import _resolve_adapter_src
    from src.api.pos_sync import _load_pkg_module
    s = _resolve_adapter_src("pinzhi")
    print("3. resolve:", s)
    m = _load_pkg_module("_diag_pz", s, ["signature", "adapter"])
    print("4. modules:", list(m.keys()))
    if "adapter" in m:
        cls = m["adapter"].PinzhiAdapter
        print("5. PinzhiAdapter:", cls)
    else:
        print("5. adapter 未加载!")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
