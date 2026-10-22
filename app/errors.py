class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Unprocessable(AppError):
    status_code = 422


class TooManyRequests(AppError):
    status_code = 429
