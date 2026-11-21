import logging
import secrets

import allure
import pytest
from core.config import MODE, CATALOG, login_type
from demo.server import NAME, SKU
from ui.pages import Auth, Shop, StoreShop

log = logging.getLogger("ui")


def require(user, *keys):
    if any(not user[key] for key in keys):
        log.warning("Отсутствуют тестовые данные")
        pytest.skip("Нужно настроить TEST_" + ", TEST_".join(k.upper() for k in keys))


def step(title):
    log.info(title)
    return allure.step(title)


def sign_in(auth, user):
    require(user, "login", "password")
    auth.start()
    auth.password_form()
    auth.submit(user["login"], user["password"])
    auth.wait_signed_in()
    if MODE == "store":
        kind = login_type(user["login"])
        field = "телефон" if kind == "phone" else "email"
        allure.dynamic.parameter("Идентификатор парольного входа", field)
        with step(f"Сверить контакт в личных данных ({field})"):
            auth.check_store_contact(kind, user["login"])
    else:
        auth.session(user["profile"])


@allure.title("AUTH-03 · Логин и пароль")
def test_email(page, target):
    with step("Войти и проверить владельца сессии"):
        sign_in(Auth(page), target[1])


@pytest.mark.parametrize("case,identifier,password,missing", [
    ("AUTH-04","empty","valid","login"), ("AUTH-05","account","empty","password"),
    ("AUTH-06","account","invalid",""), ("AUTH-07","unknown","valid",""),
    ("AUTH-FMT","malformed","valid",""),
], ids=["AUTH-04-empty-id","AUTH-05-empty-password","AUTH-06-wrong-password","AUTH-07-unknown","AUTH-FMT-invalid-email"])
@allure.title("{case} · {identifier} / {password}")
def test_rejection(page, target, case, identifier, password, missing):
    user = target[1]
    if identifier == "account" and not missing:
        require(user, "login")
    auth = Auth(page)
    with step("Отправить форму с одной ошибкой"):
        auth.start()
        auth.password_form()
        login = {
            "empty": "",
            "account": user["login"] or "case@example.invalid",
            "unknown": f"{secrets.token_hex(9)}@example.invalid",
            "malformed": "case@@example.invalid",
        }[identifier]
        # For a synthetic identifier, any nonempty password suffices.
        supplied_password = user["password"] if missing and password == "valid" else ""
        value = "" if password == "empty" else supplied_password or secrets.token_urlsafe(18)
        auth.submit(login, value)
    with step("Проверить ошибку и повторный запрос входа в кабинет"):
        auth.denied(missing)


@allure.title("MAIN-13 · Карточка линолеума из выданного каталога")
def test_catalog_product(page):
    shop = Shop(page)
    with step("Открыть отфильтрованный каталог и проверить выбранный товар"):
        shop.open(CATALOG)
        shop.open_result(SKU, NAME)
        shop.check_product(SKU, NAME)


@allure.title("E2E-01 · От входа до формы самовывоза" if MODE == "store" else "E2E-01 · От входа до создания заказа")
def test_order(page, target):
    if MODE != "demo":
        with step("Авторизоваться по логину и паролю"):
            sign_in(Auth(page), target[1])
        shop = StoreShop(page)
        with step("Найти товар по артикулу в выданном каталоге"):
            shop.open(CATALOG)
            shop.open_result(SKU, NAME)
        with step("Сверить карточку, количество и стоимость корзины"):
            price = shop.check_product(SKU, NAME)
            shop.cart(SKU, NAME, price)
        with step("Проверить оформление самовывоза"):
            shop.pickup(price * 3)
        return
    user = target[1]
    auth, shop = Auth(page), Shop(page)
    with step("Авторизоваться"):
        sign_in(auth, user)
    with step("Найти товар по артикулу"):
        shop.search(SKU, NAME)
    with step("Проверить карточку и добавить товар"):
        price = shop.product(SKU, NAME)
        assert price == 1028
    with step("Проверить вариант, количество, цену и сумму"):
        shop.line(NAME, price)
    with step("Оформить самовывоз и проверить сохранённый заказ"):
        number = shop.checkout(user)
        page.reload()
        shop.line(NAME, price)
        allure.attach(number, "Номер учебного заказа", allure.attachment_type.TEXT)


@allure.title("MAIN-14 · Добавление выбранного линолеума в гостевую корзину")
def test_store_cart(page):
    if MODE != "store":
        pytest.skip("Целевой сайт — Гипермаркет ДОМ")
    shop = StoreShop(page)
    with step("Открыть карточку из каталога"):
        shop.open(CATALOG)
        shop.open_result(SKU, NAME)
        price = shop.check_product(SKU, NAME)
    with step("Проверить товар, площадь, длину и сумму в корзине"):
        shop.cart(SKU, NAME, price)


@allure.title("MAIN-01 · Поиск линолеума по артикулу")
def test_search(page):
    shop = Shop(page)
    with step("Найти артикул через поиск и проверить карточку"):
        shop.search(SKU, NAME)
        shop.check_product(SKU, NAME)
