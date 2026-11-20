from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature


LANGUAGE = ContextVar("language", default="zh")


def message(zh, en, language=None):
    return en if (LANGUAGE.get() if language is None else language) == "en" else zh


@contextmanager
def use_language(language):
    token = LANGUAGE.set(language)
    try:
        yield
    finally:
        LANGUAGE.reset(token)


def localized(function):
    params = signature(function)

    @wraps(function)
    async def wrapped(*args, **kwargs):
        language = params.bind(*args, **kwargs).arguments.get("language", "zh")
        with use_language(language):
            return await function(*args, **kwargs)

    return wrapped
