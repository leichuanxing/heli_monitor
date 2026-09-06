from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    request = context.get("request")
    details = response.data
    message = (
        str(details.get("detail", "请求处理失败")) if isinstance(details, dict) else "请求处理失败"
    )
    response.data = {
        "code": str(getattr(exc, "default_code", "API_ERROR")).upper(),
        "message": message,
        "details": details,
        "request_id": getattr(request, "request_id", ""),
    }
    return response
