import logging
import os
import sys
import threading
import warnings
from getpass import GetPassWarning, getpass

import allure
import pytest
from playwright.sync_api import sync_playwright
from core.config import BROWSER, MODE, TIMEOUT, account, login_type
from demo.server import server

log = logging.getLogger("ui")
log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def prompt_login_credentials(user):
    if not sys.stdin.isatty():
        pytest.exit("Для скрытого ввода запустите pytest с -s в обычном терминале.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            user["login"] = getpass("Логин аккаунта, номер телефона или email (скрыто): ").strip()
            user["password"] = getpass("Пароль аккаунта (скрыто): ")
    except (EOFError, GetPassWarning):
        pytest.exit("Терминал не поддерживает скрытый ввод. Запустите pytest с -s в обычном терминале.")
    if not user["login"] or not user["password"]:
        pytest.exit("Для этих проверок нужно ввести логин и пароль.")


@pytest.fixture(scope="session")
def target():
    user = account()
    if MODE == "store":
        if os.getenv("PROMPT_EMAIL") == "1" or os.getenv("PROMPT_LOGIN") == "1":
            prompt_login_credentials(user)
        if user["login"] and login_type(user["login"]) is None:
            pytest.exit("Укажите телефон или email аккаунта для парольного входа.")
        yield os.getenv("BASE_URL", "https://gipermarketdom.ru"), user
        return
    with server(user) as app:
        thread = threading.Thread(target=app.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{app.server_port}", user
        finally:
            app.shutdown()
            thread.join()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        instance = getattr(pw, BROWSER).launch(
            headless=os.getenv("HEADED") != "1",
            executable_path=os.getenv("BROWSER_BINARY"),
            slow_mo=int(os.getenv("SLOW_MO_MS", "0")),
        )
        yield instance
        instance.close()


@pytest.fixture
def page(target, browser, request):
    with browser.new_context(base_url=target[0]) as context:
        tab = context.new_page()
        tab.set_default_timeout(TIMEOUT)
        tab.set_default_navigation_timeout(int(os.getenv("NAV_TIMEOUT_MS", "60000")))
        allure.dynamic.parameter("Среда", MODE)
        request.node.tab = tab
        tab.on("popup", lambda popup: setattr(request.node, "tab", popup))
        yield tab


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        log.error("Сбой %s на этапе %s", item.name, report.when)
        tab = getattr(item, "tab", None)
        if tab and not tab.is_closed():
            try:
                # Hide user-entered content, profile text, contact details and images.
                shot = tab.screenshot(style="*{color:transparent!important;text-shadow:none!important;background-image:none!important} input,textarea,select,img,svg,canvas,iframe{visibility:hidden!important}",timeout=4000)
                allure.attach(shot, "Состояние страницы", allure.attachment_type.PNG)
                return
            except Exception:
                pass
        allure.attach("Страница недоступна для снимка", "Диагностика")
