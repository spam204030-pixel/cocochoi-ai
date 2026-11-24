"""오류 코드와 한국어 안내 문구를 한 곳에 모은다 (설계서 6장 오류 응답 형식).

모든 오류 응답은 같은 모양이다:
    {"error": {"code": "...", "message": "대표님이 읽는 한국어 안내", "action": "해결 방법",
               "detail": "개발용 원인", "error_id": "로그에서 찾을 번호"}}
"""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    AI_KEY_MISSING = "AI_KEY_MISSING"
    AI_AUTH_FAILED = "AI_AUTH_FAILED"
    AI_CREDIT_EXHAUSTED = "AI_CREDIT_EXHAUSTED"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_BAD_OUTPUT = "AI_BAD_OUTPUT"
    STORAGE_ERROR = "STORAGE_ERROR"
    PRODUCT_IN_USE = "PRODUCT_IN_USE"
    ASSET_DUPLICATE = "ASSET_DUPLICATE"
    ASSET_IN_USE = "ASSET_IN_USE"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FFMPEG_MISSING = "FFMPEG_MISSING"
    MEDIA_UNREADABLE = "MEDIA_UNREADABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorInfo:
    status: int
    message: str
    action: str


ERRORS: dict[ErrorCode, ErrorInfo] = {
    ErrorCode.VALIDATION_ERROR: ErrorInfo(
        422, "입력한 내용에 빠지거나 잘못된 부분이 있습니다.", "표시된 칸을 확인하고 다시 입력해 주세요."
    ),
    ErrorCode.NOT_FOUND: ErrorInfo(
        404, "찾는 페이지나 자료가 없습니다.", "주소를 확인하거나 처음 화면으로 돌아가 주세요."
    ),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorInfo(
        405, "이 방법으로는 사용할 수 없는 주소입니다.", "처음 화면에서 다시 시도해 주세요."
    ),
    ErrorCode.AI_KEY_MISSING: ErrorInfo(
        400,
        "AI 사용 키가 설정되어 있지 않습니다.",
        ".env 파일에 ANTHROPIC_API_KEY를 입력한 뒤 프로그램을 다시 켜 주세요.",
    ),
    ErrorCode.AI_AUTH_FAILED: ErrorInfo(
        401,
        "AI 사용 키가 맞지 않거나 만료되었습니다.",
        "Anthropic Console에서 키를 확인하고 .env 파일의 값을 바꿔 주세요.",
    ),
    ErrorCode.AI_CREDIT_EXHAUSTED: ErrorInfo(
        402, "AI 사용 크레딧이 부족합니다.", "Anthropic Console에서 크레딧을 충전한 뒤 다시 시도해 주세요."
    ),
    ErrorCode.AI_RATE_LIMITED: ErrorInfo(
        429, "AI 사용량이 잠시 많습니다.", "1분 뒤 '다시 만들기'를 눌러 주세요."
    ),
    ErrorCode.AI_TIMEOUT: ErrorInfo(
        504, "AI 응답이 너무 오래 걸려 중단했습니다.", "'다시 만들기'를 눌러 주세요."
    ),
    ErrorCode.AI_UNAVAILABLE: ErrorInfo(
        503, "AI 서버에 연결할 수 없습니다.", "인터넷 연결을 확인한 뒤 다시 시도해 주세요."
    ),
    ErrorCode.AI_BAD_OUTPUT: ErrorInfo(
        502, "AI 결과가 형식에 맞지 않아 사용할 수 없습니다.", "해당 단계를 '다시 만들기' 해 주세요."
    ),
    ErrorCode.STORAGE_ERROR: ErrorInfo(
        500,
        "파일을 저장하거나 읽는 중에 문제가 생겼습니다.",
        "컴퓨터 저장 공간과 storage 폴더를 확인해 주세요.",
    ),
    ErrorCode.PRODUCT_IN_USE: ErrorInfo(
        409,
        "이 제품으로 만든 콘텐츠가 있어서 삭제할 수 없습니다.",
        "연결된 콘텐츠를 먼저 정리한 뒤 다시 삭제해 주세요.",
    ),
    ErrorCode.ASSET_DUPLICATE: ErrorInfo(
        409, "이미 올린 파일입니다.", "같은 파일은 한 번만 올리면 됩니다. 기존 파일을 사용해 주세요."
    ),
    ErrorCode.ASSET_IN_USE: ErrorInfo(
        409, "콘텐츠 제작에 쓰이고 있는 파일이라 삭제할 수 없습니다.", "연결된 콘텐츠를 먼저 정리해 주세요."
    ),
    ErrorCode.UNSUPPORTED_FILE: ErrorInfo(
        415,
        "올릴 수 없는 파일 형식입니다.",
        "사진은 jpg·png·webp·heic, 영상은 mp4·mov·m4v·webm 파일로 올려 주세요.",
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorInfo(
        413, "파일이 너무 큽니다.", "영상 길이를 줄이거나 화질을 낮춰서 다시 올려 주세요."
    ),
    ErrorCode.FFMPEG_MISSING: ErrorInfo(
        503,
        "영상 처리 프로그램(FFmpeg)이 설치되어 있지 않습니다.",
        "처음 화면의 설치 방법을 따라 FFmpeg를 설치한 뒤 프로그램을 다시 켜 주세요.",
    ),
    ErrorCode.MEDIA_UNREADABLE: ErrorInfo(
        422,
        "영상이나 사진 파일을 읽을 수 없습니다.",
        "파일이 손상되지 않았는지 확인하고, mp4·mov·jpg·png 파일로 다시 올려 주세요.",
    ),
    ErrorCode.INTERNAL_ERROR: ErrorInfo(
        500,
        "프로그램에 예상하지 못한 문제가 생겼습니다.",
        "다시 시도해 주세요. 계속되면 오류 번호를 알려주세요.",
    ),
}


class AppError(Exception):
    """프로그램 안에서 일부러 내는 오류. 코드만 정하면 안내 문구는 자동으로 붙는다."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else str(code))

    @property
    def info(self) -> ErrorInfo:
        return ERRORS[self.code]


def error_payload(code: ErrorCode, detail: str = "", error_id: str | None = None) -> dict:
    info = ERRORS[code]
    body = {"code": str(code), "message": info.message, "action": info.action, "detail": detail}
    if error_id:
        body["error_id"] = error_id
    return {"error": body}
