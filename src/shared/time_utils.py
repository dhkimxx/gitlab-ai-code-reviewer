from __future__ import annotations


def format_seconds(seconds: float) -> str:
    if seconds < 0:
        return "0ms"

    if seconds < 1:
        millis = int(seconds * 1000)
        return f"{millis}ms"

    if seconds < 60:
        return f"{seconds:.2f}s"

    total_seconds = int(seconds)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"

    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {seconds}s"
