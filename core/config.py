import os
import re
import secrets

MODE = os.getenv("TARGET", "store")
if MODE not in ("demo", "store"):
    raise ValueError("TARGET должен быть demo или store")
TIMEOUT = int(os.getenv("TIMEOUT_MS", "30000"))
BROWSER = os.getenv("BROWSER", "chromium")
CATALOG = "/catalog/linoleum/?filters%5B%5D=170460&prop_id_170460=белый%40серый"


def login_type(login):
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", login):
        return "email"
    if re.fullmatch(r"\+?[0-9\s().-]+", login) and len(re.sub(r"\D", "", login)) in (10, 11):
        return "phone"
    return None


def account():
    if MODE == "demo":
        return {
            "login": "student@example.test",
            "password": secrets.token_urlsafe(),
            "profile": "Учебный покупатель",
            "phone": "+79990000000",
        }
    return {
        "login": (os.getenv("TEST_LOGIN") or os.getenv("TEST_EMAIL", "")).strip(),
        "password": os.getenv("TEST_PASSWORD", ""),
    }
