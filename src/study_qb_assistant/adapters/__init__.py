"""外部客户端响应适配器模块。

该模块汇集了与外部系统（如 OCS）交互的适配器和配置构建函数。
"""

from .ocs import build_ocs_config, to_ocs_low_confidence_response, to_ocs_response

__all__ = ["build_ocs_config", "to_ocs_low_confidence_response", "to_ocs_response"]
