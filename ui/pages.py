import logging
import os
import re
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect
from core.config import TIMEOUT, CATALOG, MODE

log = logging.getLogger("ui")
expect.set_options(timeout=TIMEOUT)


class BaseElement:
    def __init__(self, locator, name):
        self.locator, self.name = locator, name

    def act(self, method, *args):
        with allure.step(f"{self.name} · {method}"):
            log.debug("Ожидание элемента %s", self.name)
            try:
                self.locator.wait_for(state="visible")
                getattr(self.locator, method)(*args)
            except Exception:
                raise AssertionError(f"Ошибка действия {method}, элемент «{self.name}»") from None


class PageObject:
    def __init__(self, page):
        self.page = page

    def element(self, selector, name):
        return BaseElement(self.page.locator(selector), name)

    @contextmanager
    def handle_cookie_banner(self):
        page = self.page
        accept = page.locator(".cookie_block_1_v3").get_by_text("Принять все", exact=True)
        page.add_locator_handler(accept, lambda button: button.click())
        try:
            yield
        finally:
            page.remove_locator_handler(accept)

    def open(self, path):
        self.page.goto(path, wait_until="domcontentloaded")
        challenge = self.page.get_by_text("Please fill out the CAPTCHA", exact=False)
        if challenge.is_visible():
            if os.getenv("HEADED") != "1":
                raise AssertionError("Магазин запросил CAPTCHA. Для ручной проверки запустите HEADED=1.")
            log.warning("Пройдите CAPTCHA в открытом Chromium")
            challenge.wait_for(state="hidden", timeout=180000)


class Auth(PageObject):
    def start(self):
        self.open("/personal_new/")
        self.page.locator(".auth__tab[data-type=login]:visible").wait_for()

    def password_form(self):
        self.element('.auth__tab[data-type=login]:visible', 'По логину').act("click")

    def submit(self, login, password):
        self.element("#auth-form-login-login", "Логин").act("fill", login)
        self.element("#auth-form-login-password", "Пароль").act("fill", password)
        self.element('form:has(#auth-form-login-login) button', 'Войти').act("click")

    def wait_signed_in(self):
        self.page.locator("#auth-form-login-login:visible").wait_for(state="hidden")

    def session(self, profile):
        self.open("/personal_new/")
        try:
            expect(self.page.get_by_text(profile, exact=True)).to_be_visible()
        except Exception:
            raise AssertionError("В кабинете отсутствует маркер тестового пользователя") from None

    def check_store_contact(self, kind, login):
        self.open("/cabinet/")
        with self.handle_cookie_banner():
            self.page.locator('a.cabinet__section[href="/cabinet/personal/"]').click()
        if kind == "phone":
            field = self.page.locator('input[name="phone"][type="tel"]:visible')
            digits = re.sub(r"\D", "", login)[-10:]
            expected = re.compile(r"^\D*(?:[78]\D*)?" + r"\D*".join(digits) + r"\D*$")
            label = "Телефон"
        else:
            field = self.page.locator('input[name="EMAIL"]:visible')
            expected = re.compile(r"^\s*" + re.escape(login) + r"\s*$", re.I)
            label = "Email"
        field.wait_for(state="visible")
        try:
            expect(field).to_have_value(expected)
        except AssertionError:
            if not field.input_value().strip():
                raise AssertionError(f"{label}: поле в личных данных осталось пустым") from None
            raise AssertionError(f"{label} в личных данных отличается от ожидаемого значения") from None

    def denied(self, missing):
        if missing:
            field = self.page.locator("#auth-form-login-" + missing)
            expect(field).to_have_js_property("willValidate", True)
            assert field.evaluate("e => e.validity.valueMissing && !!e.validationMessage")
        else:
            expect(self.page.locator("form:has(#auth-form-login-login) .form__errors")).to_have_text(re.compile("неверн|неправильн|ошиб", re.I))
        self.start()


class Shop(PageObject):
    def search(self, sku, name):
        self.open(CATALOG)
        if MODE == "store":
            expect(self.page.get_by_role("heading", level=1, name=re.compile("Линолеум"))).to_be_visible()
            header = self.page.locator('form.sform input.digi-instant-search[name="qs"]:visible')
            try:
                header.wait_for(state="visible")
            except PlaywrightTimeoutError:
                raise AssertionError("Поисковый виджет Diginetica не загрузился") from None
            cookies = self.page.locator(".cookie_block_1_v3").get_by_text("Принять все", exact=True)
            if cookies.is_visible():
                cookies.click()
            BaseElement(header, "Поиск в шапке").act("click")
            panel = self.page.locator(".digi-is-container:visible")
            active_box = self.page.locator(
                ".digi-is-container:visible input.digi-search-form__input:focus, "
                "form.sform input.digi-instant-search[name=qs]:focus"
            )
            BaseElement(active_box, "Артикул").act("fill", sku)
            submit = panel.locator("button.digi-search-form__submit:visible")
            if submit.is_visible():
                BaseElement(submit, "Найти").act("click")
            else:
                BaseElement(active_box, "Отправить запрос").act("press", "Enter")
            self.page.wait_for_url(lambda url: any(
                parse_qs(urlsplit(url).query).get(key) == [sku] for key in ("term", "qs", "q")
            ))
            if panel.is_visible():
                result = panel.locator(f'a[href*="_{sku}/"]:visible').filter(has_text=name)
                self.open_product_link(result, "Товар в поисковой выдаче")
            else:
                # Distinguish SKU search results from the unfiltered catalogue.
                codes = self.page.locator('button.card-previwe__basket[data-local-code]:visible')
                expect(codes).not_to_have_count(0)
                assert set(codes.evaluate_all("els => els.map(e => e.dataset.localCode)")) == {sku}, "Выдача содержит другие артикулы"
                self.open_result(sku, name)
            return
        search = self.element("#title-search-input:visible", "Поиск по артикулу")
        search.act("fill", sku)
        search.act("press", "Enter")
        self.page.wait_for_url(lambda url: "search" in url or "qs=" in url)
        self.open_result(sku, name)

    def open_result(self, sku, name):
        link = self.page.locator(f'a[href$="_{sku}/"]:visible').filter(has_text=name)
        self.open_product_link(link, "Ссылка на товар")

    def open_product_link(self, locator, name):
        link = BaseElement(locator, name)
        with self.handle_cookie_banner():
            if locator.get_attribute("target") == "_blank":
                with self.page.expect_popup() as popup:
                    link.act("click")
                self.page = popup.value
            else:
                link.act("click")

    def check_product(self, sku, name):
        expect(self.page.locator("h1")).to_have_text(name)
        expect(self.page.locator("#card-article")).to_contain_text(sku)
        price = self.page.locator(".card-price__price:visible").inner_text()
        assert re.fullmatch(r"[\d\s]+\s*₽/м²", price)
        return int(re.sub(r"\s", "", price.split("₽")[0]))

    def product(self, sku, name):
        price = self.check_product(sku, name)
        with self.handle_cookie_banner():
            self.element(f'button.btn.addToCart[data-local-code="{sku}"]', "В корзину").act("click")
            self.page.get_by_text("Перейти корзину", exact=True).click()
        return price

    def line(self, name, price):
        for selector, value in [("#item",name),("#qty","3 м²"),("#price",f"{price} ₽/м²"),("#total",f"{3*price} ₽")]:
            expect(self.page.locator(selector)).to_have_text(value)

    def checkout(self, user):
        self.page.get_by_text("Оформить заказ", exact=True).click()
        for field, value in [("recipient",user["profile"]),("phone",user["phone"])]:
            self.element(f"input[name={field}]",field).act("fill", value)
        for field, value in [("delivery","Самовывоз"),("payment","При получении")]:
            self.element(f"select[name={field}]",field).act("select_option", value)
        self.element("[name=consent]", "Согласие").act("check")
        self.element("form button","Подтвердить заказ").act("click")
        expect(self.page.locator("h1")).to_have_text("Заказ создан")
        number = self.page.locator("#number")
        expect(number).to_have_text(re.compile(r"[a-f0-9]{10}"))
        return number.inner_text()


class StoreShop(Shop):
    def cart(self, sku, name, price):
        product_url = self.page.url
        self.open("/personal_new/cart-buyer/")
        rows = self.page.locator(".basket-element__items .c_cart_tr:visible")
        empty = self.page.locator(".c-basket__empty__title:visible")
        expect(empty.or_(rows.first)).to_be_visible()
        if empty.is_visible():
            self.open(product_url)
            self.product(sku, name)
            rows.first.wait_for(state="visible")
        for row in rows.all():
            self.check_cart_row(row, sku, name, price)
        if rows.count() > 1:
            self.remove_duplicate_rows(rows)
            self.page.reload(wait_until="domcontentloaded")
            expect(rows).to_have_count(1)
            self.check_cart_row(rows, sku, name, price)
        expect(rows).to_have_count(1)
        self.amount(self.page.locator(".sum_pay:visible"), price * 3)

    def check_cart_row(self, row, sku, name, price):
        position = row.locator(f'a.name-link[href$="_{sku}/"]:visible').filter(has_text=name)
        if position.count() != 1:
            raise AssertionError(f"В корзине есть другой товар. Для теста нужен артикул {sku}.")
        expect(position).to_contain_text(sku)
        expect(position).to_contain_text(re.compile(r"Площадь:\s*3[.,]00"))
        expect(position).to_contain_text(re.compile(r"Длина:\s*1[.,]00"))
        self.amount(row.locator(".sum_once:visible"), price)
        self.amount(row.locator(".sum_line:visible"), price * 3)

    def remove_duplicate_rows(self, rows):
        row_ids = rows.evaluate_all("elements => elements.map(element => element.dataset.id ?? '')")
        assert all(key.isdecimal() for key in row_ids) and len(set(row_ids)) == len(row_ids), (
            "Строки корзины не удалось однозначно различить"
        )
        selected = rows.filter(has=self.page.locator(".c_cart_check:checked"))
        keep = selected.first.get_attribute("data-id") if selected.count() else row_ids[0]

        def confirm_removal(dialog):
            if dialog.type == "confirm" and dialog.message.strip() == "Удалить товар из корзины?":
                dialog.accept()
            else:
                dialog.dismiss()

        for row_id in row_ids:
            if row_id == keep:
                continue
            duplicate = rows.and_(self.page.locator(f'[data-id="{row_id}"]'))
            with allure.step("Удалить подтверждённый дубль товара"):
                self.page.on("dialog", confirm_removal)
                try:
                    duplicate.locator(".c_cart_del:visible").click()
                    expect(duplicate).to_have_count(0)
                finally:
                    self.page.remove_listener("dialog", confirm_removal)

    def amount(self, locator, expected):
        digits = r"\s*".join(str(expected))
        expect(locator).to_have_text(re.compile(rf"^\s*{digits}(?:[.,]0+)?\s*₽\s*$"))

    def pickup(self, total):
        self.page.get_by_role("link", name="Оформить самовывоз").click()
        expect(self.page.locator("h1")).to_have_text("Оформление заказа")
        for field in ("sale_order_delivery_name", "sale_order_delivery_phone"):
            expect(self.page.locator(f'input[name="{field}"]:visible')).to_be_visible()
        self.amount(self.page.locator(".sum_pay:visible"), total)
        expect(self.page.locator(".make_order_self")).to_have_text("Оформить заказ")
