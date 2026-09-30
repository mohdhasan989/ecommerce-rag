import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app")
CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR"}


def _resp(status, code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def register_handlers(app: FastAPI):
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(_: Request, e: StarletteHTTPException):
        return _resp(e.status_code, CODES.get(e.status_code, "ERROR"), str(e.detail))

    @app.exception_handler(RequestValidationError)
    async def val_exc(_: Request, e: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in x["loc"][1:]), "message": x["msg"]} for x in e.errors()]
        return _resp(422, "VALIDATION_ERROR", "Please check the submitted data.", details)

    @app.exception_handler(SQLAlchemyError)
    async def db_exc(_: Request, e: SQLAlchemyError):
        log.exception("Database error")
        return _resp(500, "DATABASE_ERROR", "A database error occurred. Please try again later.")

    @app.exception_handler(Exception)
    async def any_exc(_: Request, e: Exception):
        log.exception("Unhandled error")
        return _resp(500, "SERVER_ERROR", "Something went wrong. Please try again later.")
