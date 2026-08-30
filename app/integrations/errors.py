class CustomerSystemError(Exception):
    pass


class CustomerSystemTimeoutError(CustomerSystemError):
    def __init__(self, attempts: int) -> None:
        super().__init__("Customer system request timed out")
        self.attempts = attempts


class CustomerSystemUnavailableError(CustomerSystemError):
    def __init__(self, attempts: int, upstream_status: int | None = None) -> None:
        super().__init__("Customer system is temporarily unavailable")
        self.attempts = attempts
        self.upstream_status = upstream_status


class CustomerSystemResponseError(CustomerSystemError):
    def __init__(self, upstream_status: int) -> None:
        super().__init__("Customer system rejected the request")
        self.upstream_status = upstream_status
