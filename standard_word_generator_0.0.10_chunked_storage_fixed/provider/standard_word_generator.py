from dify_plugin import ToolProvider


class StandardWordGeneratorProvider(ToolProvider):
    def validate_credentials(self, credentials: dict) -> None:
        return None
