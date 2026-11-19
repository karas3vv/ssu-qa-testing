"""Локальный магазин для демонстрации входа по email и тестового заказа."""
import html
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SKU = "1203021011"
NAME = "Линолеум полукоммерческий Ideal IMPERIA ARONA 6_176L, 3м"
PRICE = 1028


def server(account):
    sessions, orders = {}, {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", f"sid={self.sid}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(('<!doctype html><meta charset=utf-8><title>ДОМ · учебный стенд</title>' + body).encode())

        def dispatch(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            sid = cookie["sid"].value if "sid" in cookie else ""
            self.sid = sid if sid in sessions else secrets.token_hex(24)
            state = sessions.setdefault(self.sid, {"user": False, "qty": 0})
            url = urlsplit(self.path)
            path = url.path
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()).items()}
            error = ""
            if path == "/login":
                state["user"] = form.get("login") == account["login"] and form.get("passw") == account["password"]
                error = "" if state["user"] else "Неверный логин или пароль"
            if path in ("/login", "/personal_new/") and state["user"]:
                return self.respond('<h1>Личный кабинет</h1><span id="profile-name">' + html.escape(account["profile"]) + '</span><a href="/catalog/linoleum/">Каталог</a>')
            if path in ("/login", "/personal_new/"):
                return self.respond(f'''<div class="auth">
                <button class="auth__tab" data-type="login" onclick="document.getElementById('login').hidden=false">По логину</button>
                <form id="login" action="/login" method="post" {"" if error else "hidden"}><input id="auth-form-login-login" name="login" required>
                <input id="auth-form-login-password" name="passw" type="password" required><div class="form__errors">{error}</div><button>Войти</button></form></div>''')
            if path == "/catalog/linoleum/":
                return self.respond(f'<h1>Линолеум</h1><form action="/search/"><input id="title-search-input" name="qs"><button>Найти</button></form><a href="/catalog/item_{SKU}/">{NAME}</a>')
            if path == "/search/":
                found = parse_qs(url.query).get("qs") == [SKU]
                return self.respond('<h1>Результаты поиска</h1>' + (f'<a href="/catalog/item_{SKU}/">{NAME}</a>' if found else "Ничего не найдено"))
            if path == f"/catalog/item_{SKU}/":
                return self.respond(f'<h1>{NAME}</h1><div id="card-article">ЛК: {SKU}</div><div class="card-price__price">{PRICE} ₽/м²</div><form action="/add" method="post"><button class="btn addToCart" data-local-code="{SKU}">В корзину</button></form>')
            if not state["user"]:
                return self.respond('<a href="/personal_new/">Войти</a>')
            if path == "/add" and self.command == "POST":
                state["qty"] += 3
                return self.respond('<a href="/personal_new/cart-buyer/">Перейти корзину</a>')
            qty = state["qty"]
            line = f'<div id="item">{NAME}</div><div id="qty">{qty} м²</div><div id="price">{PRICE} ₽/м²</div><div id="total">{qty * PRICE} ₽</div>'
            if path == "/personal_new/cart-buyer/":
                return self.respond(line + '<a href="/checkout">Оформить заказ</a>')
            if path == "/checkout" and qty:
                return self.respond('<form method="post" action="/order"><input name="recipient" required><input type="tel" name="phone" required><select name="delivery"><option>Самовывоз</option></select><select name="payment"><option>При получении</option></select><label><input type="checkbox" name="consent" required>Согласие</label><button>Подтвердить заказ</button></form>')
            if path == "/order" and qty and all(form.get(k) for k in ("recipient","phone","delivery","payment","consent")):
                number = secrets.token_hex(5)
                orders[number] = (self.sid, line)
                state["qty"] = 0
                self.send_response(303)
                self.send_header("Location", "/order/" + number)
                self.end_headers()
                return
            number = path.removeprefix("/order/")
            if number in orders and orders[number][0] == self.sid:
                return self.respond(f'<h1>Заказ создан</h1><div id="number">{number}</div>' + orders[number][1])
            self.send_error(404)

        do_GET = do_POST = dispatch

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
