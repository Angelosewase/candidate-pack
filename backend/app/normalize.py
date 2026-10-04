"""Normalisation shared by the CSV import and the API, so that a request for
"Pick  Cup" and an imported episode with task " PICK CUP " match each other."""

import re

_WS = re.compile(r"\s+")


def normalize_task_name(value: str) -> str:
    return _WS.sub(" ", value).strip().lower()


def normalize_email(value: str) -> str:
    return value.strip().lower()
