import ast
import math
import operator
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain.tools import tool


MAX_EXPRESSION_LENGTH = 200
MAX_ABSOLUTE_VALUE = 1_000_000_000_000_000
MAX_EXPONENT = 12

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _validate_result(value: int | float) -> int | float:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("The calculation produced a non-finite result")
    if abs(value) > MAX_ABSOLUTE_VALUE:
        raise ValueError("The calculation result is too large")
    return value


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _validate_result(node.value)

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _validate_result(_UNARY_OPERATORS[type(node.op)](_evaluate(node.operand)))

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError("The exponent is too large")
        return _validate_result(_BINARY_OPERATORS[type(node.op)](left, right))

    raise ValueError("Only numbers, parentheses, and arithmetic operators are allowed")


@tool
def calculator(expression: str) -> str:
    """Safely calculate an arithmetic expression using +, -, *, /, //, %, and **."""
    if not expression.strip():
        raise ValueError("The expression cannot be empty")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError("The expression is too long")

    try:
        parsed = ast.parse(expression, mode="eval")
        result = _evaluate(parsed.body)
    except (SyntaxError, TypeError, ZeroDivisionError) as exc:
        raise ValueError("The arithmetic expression is invalid") from exc

    return str(result)


@tool
def current_datetime(timezone_name: str = "Europe/Istanbul") -> str:
    """Return the current date and time in an IANA timezone such as Europe/Istanbul."""
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc

    current = datetime.now(timezone)
    return (
        f"timezone={timezone_name}; "
        f"date={current.date().isoformat()}; "
        f"time={current.strftime('%H:%M:%S')}; "
        f"utc_offset={current.strftime('%z')[:3]}:{current.strftime('%z')[3:]}"
    )


SYSTEM_TOOLS = [calculator, current_datetime]
SYSTEM_TOOL_MAP = {item.name: item for item in SYSTEM_TOOLS}
