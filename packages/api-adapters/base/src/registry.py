"""
POS 适配器注册表

提供工厂函数 get_transformer()，按 pos_type 返回对应适配器实例。
新增 POS 系统只需：
  1. 实现 to_order() 和 to_staff_action()
  2. 在 POS_REGISTRY 中注册

不需要修改任何业务逻辑代码。
"""
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()

# POS 系统注册表（pos_type → 适配器类路径）
# None 表示尚未实现，调用时会返回 NotImplementedError（有明确错误提示）
POS_REGISTRY: Dict[str, Optional[str]] = {
    "aoqiwei": "packages.api-adapters.aoqiwei.src.adapter.AoqiweiAdapter",
    "pinzhi": "packages.api-adapters.pinzhi.src.adapter.PinzhiAdapter",
    "meituan": "packages.api-adapters.meituan-saas.src.adapter.MeituanSaasAdapter",
    "tiancai": "packages.api-adapters.tiancai-shanglong.src.adapter.TiancaiShanglongAdapter",
    "keruyun": "packages.api-adapters.keruyun.src.adapter.KeruyunAdapter",
}


class AdapterNotImplementedError(NotImplementedError):
    """适配器未实现错误"""
    def __init__(self, pos_type: str):
        super().__init__(
            f"POS 适配器 '{pos_type}' 尚未实现。"
            f"请实现 to_order() 和 to_staff_action() 后在 POS_REGISTRY 中注册。"
        )
        self.pos_type = pos_type


def get_transformer(pos_type: str, store_id: str, brand_id: str, config: Optional[Dict[str, Any]] = None):
    """
    POS 适配器工厂函数

    Args:
        pos_type: POS 系统类型（如 "aoqiwei", "pinzhi"）
        store_id: 门店ID
        brand_id: 品牌ID
        config: 适配器配置字典（base_url、api_key 等）

    Returns:
        BaseAdapter 子类实例

    Raises:
        ValueError: pos_type 不在注册表中
        AdapterNotImplementedError: 适配器尚未实现（在注册表中但值为 None）
    """
    if pos_type not in POS_REGISTRY:
        registered = list(POS_REGISTRY.keys())
        raise ValueError(
            f"未知的 POS 系统类型: '{pos_type}'。已注册类型: {registered}"
        )

    adapter_path = POS_REGISTRY[pos_type]
    if adapter_path is None:
        raise AdapterNotImplementedError(pos_type)

    # 动态导入适配器类
    module_path, class_name = adapter_path.rsplit(".", 1)
    # 将包路径中的 - 替换为 _ 以兼容 Python 模块命名
    module_path = module_path.replace("-", "_")

    import importlib
    try:
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        logger.error("适配器加载失败", pos_type=pos_type, module_path=module_path, error=str(e))
        raise ImportError(f"无法加载 POS 适配器 '{pos_type}': {e}") from e

    cfg = config or {}
    cfg.setdefault("store_id", store_id)
    cfg.setdefault("brand_id", brand_id)

    logger.info("POS 适配器实例化", pos_type=pos_type, store_id=store_id, brand_id=brand_id)
    return adapter_class(cfg)


def list_registered_pos_types() -> list:
    """返回所有已注册的 POS 系统类型（包括未实现的）"""
    return list(POS_REGISTRY.keys())


def list_implemented_pos_types() -> list:
    """返回已实现的 POS 系统类型"""
    return [k for k, v in POS_REGISTRY.items() if v is not None]
