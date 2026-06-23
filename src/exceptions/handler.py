from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from exceptions.custom_exception import CustomException
from exceptions.file_not_found_exception import FileNotFoundException
from exceptions.invalid_parameter_exception import InvalidParameterException
from python_library.logger.app_logger import AppLogger
from response.error_response import ErrorResponse


def _normalize_validation_loc(loc: tuple[Any, ...] | list[Any]) -> str:
    parts = [str(part) for part in loc]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts)


def _build_field_error_response(
    exc: InvalidParameterException | FileNotFoundException,
) -> JSONResponse:
    ec = exc.error_code
    response = (
        ErrorResponse.create()
        .with_error_code(ec)
        .with_message(str(exc))
        .with_field_errors(exc.field_errors)
    )
    return JSONResponse(status_code=ec.status, content=response.to_dict())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            {
                "field": _normalize_validation_loc(error.get("loc", [])),
                "value": error.get("input"),
                "reason": error.get("msg", ""),
            }
            for error in exc.errors()
        ]
        return _build_field_error_response(InvalidParameterException(field_errors))

    @app.exception_handler(InvalidParameterException)
    async def handle_invalid_parameter_exception(
        request: Request, exc: InvalidParameterException
    ) -> JSONResponse:
        return _build_field_error_response(exc)

    @app.exception_handler(FileNotFoundException)
    async def handle_file_not_found_exception(
        request: Request, exc: FileNotFoundException
    ) -> JSONResponse:
        return _build_field_error_response(exc)

    @app.exception_handler(CustomException)
    async def handle_custom_exception(
        request: Request, exc: CustomException
    ) -> JSONResponse:
        ec = exc.error_code
        response = ErrorResponse.create().with_error_code(ec)
        response.message = str(exc)
        return JSONResponse(status_code=ec.status, content=response.to_dict())

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        AppLogger.instance().exception(
            f"Unhandled exception on {request.method} {request.url}", exc
        )
        response = (
            ErrorResponse.create()
            .with_status(500)
            .with_message("Internal server error")
        )
        return JSONResponse(status_code=500, content=response.to_dict())
