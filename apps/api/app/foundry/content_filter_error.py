from .api_error import FoundryApiError


class FoundryContentFilterError(FoundryApiError):
    def __init__(
        self,
        status_code: int,
        *,
        code: str,
        inner_code: str | None,
        categories: list[str],
        source: str,
    ) -> None:
        super().__init__(
            status_code,
            code,
            "Azure Foundry content policy blocked the request",
        )
        self.inner_code = inner_code
        self.categories = categories
        self.source = source
