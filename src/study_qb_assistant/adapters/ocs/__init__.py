"""OCS 集成模块公开入口。"""

from .config import build_ocs_config, render_ocs_client_script
from .contracts import OcsIntegrationPort
from .integration import DefaultOcsIntegration
from .registry import OcsQuestionTypeRegistry
from .request import parse_ocs_request
from .response import to_ocs_low_confidence_response, to_ocs_response
from .question_types import BaseOcsQuestionTypeHandler, OcsFormattedAnswer

__all__ = [
    "BaseOcsQuestionTypeHandler",
    "DefaultOcsIntegration",
    "OcsFormattedAnswer",
    "OcsIntegrationPort",
    "OcsQuestionTypeRegistry",
    "build_ocs_config",
    "parse_ocs_request",
    "render_ocs_client_script",
    "to_ocs_low_confidence_response",
    "to_ocs_response",
]
