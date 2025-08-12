# parsing/parsers/lemanapro.py
import re
import os
import json
import difflib
import tempfile
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(page):
        return

from . import register_parser

BASE = "https://lemanapro.ru"
DEBUG_DIR = tempfile.gettempdir()

# Реалистичный десктопный UA (без HeadlessChrome)
REAL_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    'sec-ch-ua': '"Google Chrome";v="125", "Chromium";v="125", "Not:A-Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}


def normalize(text):
    return re.sub(r"\W+", "", str(text or "").lower()).strip()


def parse_rub_price(text):
    if not text:
        return "Н/Д"
    s = str(text).replace("\xa0", " ").strip()
    s = re.sub(r"[^\d.,]", "", s)
    m = re.search(r"(\d{1,3}(?:[ \d]{0,3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)", s)
    if not m:
        digits = re.findall(r"\d+", s)
        return int("".join(digits)) if digits else "Н/Д"
    num = m.group(1).replace(" ", "").replace(",", ".")
    try:
        val = float(num)
        return int(round(val))
    except:
        digits = re.findall(r"\d+", num)
        return int("".join(digits)) if digits else "Н/Д"


def is_challenge_html(html: str) -> bool:
    low = html.lower()
    return any(s in low for s in [
        "ddos-guard", "checking your browser", "/cdn-cgi/challenge",
        "captcha", "just a moment", "server error"
    ])


async def maybe_pass_challenge(page):
    html = await page.content()
    if is_challenge_html(html):
        await page.wait_for_timeout(7000)
        try:
            await page.reload(timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(800)
        except:
            pass


async def goto_with_retries(page, url, tries=3, tag=""):
    last_resp = None
    for attempt in range(tries):
        try:
            last_resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(400)
        except:
            last_resp = None

        html = await page.content()
        status = last_resp.status if last_resp else None
        bad = is_challenge_html(html) or (status and status >= 500)

        if not bad and html.strip():
            return last_resp

        if attempt < tries - 1:
            await page.wait_for_timeout(1200 * (attempt + 1))
            try:
                await page.reload(timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(300)
            except:
                pass

    return last_resp


async def safe_click_button(page, selectors, timeout=2000):
    # Кликаем только кнопки, чтобы не словить навигацию по <a>
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                if tag != "button":
                    continue
                await el.scroll_into_view_if_needed()
                await el.click(timeout=timeout)
                await page.wait_for_timeout(500)
                return True
        except:
            continue
    return False


async def auto_scroll(page, max_rounds=30, sleep_ms=700):
    last_h = 0
    for _ in range(max_rounds):
        try:
            h = await page.evaluate("document.body ? document.body.scrollHeight : 0")
        except:
            h = 0
        await page.mouse.wheel(0, h or 1500)
        await page.wait_for_timeout(sleep_ms)
        try:
            new_h = await page.evaluate("document.body ? document.body.scrollHeight : 0")
        except:
            new_h = 0
        if new_h <= last_h:
            break
        last_h = new_h


def extract_pagination_urls_from_html(html, current_url):
    """
    Собираем все ссылки пагинации:
    - rel=next
    - ?PAGEN_*
    - ?page=N (как на lemanapro)
    Возвращаем отсортированный список по номеру страницы.
    """
    soup = BeautifulSoup(html, "lxml")
    found = set()

    # rel=next
    next_el = soup.select_one('a[rel="next"], link[rel="next"]')
    if next_el and next_el.get("href"):
        found.add(urljoin(current_url, next_el.get("href")))

    # Bitrix и общий ?page=
    for a in soup.select('a[href*="PAGEN_"], a[href*="?page="], a[href*="&page="], li[data-testid="pagination-list-item"] a[href]'):
        href = a.get("href")
        if href:
            found.add(urljoin(current_url, href))

    def page_num(u):
        m = re.search(r'(?:[?&]page=)(\d+)', u)
        return int(m.group(1)) if m else (1 if urlparse(u).path == urlparse(current_url).path else 0)

    return sorted(found, key=page_num)


async def collect_links(page, category_url):
    await goto_with_retries(page, category_url, tries=3, tag="category")
    await maybe_pass_challenge(page)

    # Баннеры/куки
    await safe_click_button(page, [
        'button:has-text("Принять")',
        'button:has-text("Согласен")',
        'button:has-text("Да")',
        'button:has-text("Ок")',
        'button:has-text("Понятно")',
    ], timeout=1500)

    # На этом сайте нет "Показать ещё", оставим прокрутку минимально для прогрузки
    await auto_scroll(page, max_rounds=5, sleep_ms=400)

    html = await page.content()
    first_title = ""
    try:
        first_title = await page.title()
    except:
        pass

    # Инициализируем очередь страниц пагинации
    to_visit = []
    visited_pages = set()
    initial_pages = [category_url] + extract_pagination_urls_from_html(html, category_url)
    # Уберём дубликаты, сохраним порядок
    seen = set()
    for u in initial_pages:
        if u not in seen:
            seen.add(u)
            to_visit.append(u)

    links = set()
    empty_pages_seen = 0
    MAX_PAGES = 100  # защита от бесконечного обхода

    while to_visit and len(visited_pages) < MAX_PAGES:
        page_url = to_visit.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        await goto_with_retries(page, page_url, tries=3, tag="category_page")
        await maybe_pass_challenge(page)
        await page.wait_for_timeout(200)

        # Собираем ссылки на товары
        try:
            hrefs = await page.evaluate("""() => Array.from(document.querySelectorAll('a[href*="/product/"]'))
                .map(a => a.getAttribute('href')).filter(Boolean)""")
        except:
            hrefs = []

        added = 0
        for h in hrefs or []:
            u = urljoin(BASE, h)
            if any(x in u for x in ["#", "/compare", "/favorites", "/filter/", "?PAGEN_"]):
                continue
            # только реальные карточки
            parts = urlparse(u).path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "product":
                if u not in links:
                    links.add(u)
                    added += 1

        # Пустые хвостовые страницы — просто учитываем и продолжаем
        if added == 0:
            empty_pages_seen += 1

        # На каждой странице расширяем список страниц пагинации
        page_html = await page.content()
        more_pages = extract_pagination_urls_from_html(page_html, page_url)
        for u in more_pages:
            if u not in visited_pages and u not in to_visit:
                to_visit.append(u)

        # Немного подождать перед следующей страницей
        await page.wait_for_timeout(150)

        # Если много страниц оказались пустыми подряд — можно ускориться, но не прерываемся жёстко
        if empty_pages_seen >= 5 and len(visited_pages) > 5:
            # вероятно, достигли хвоста
            break

    blocked = is_challenge_html(await page.content())
    return list(links), {
        "title": first_title,
        "blocked": blocked,
        "pages_visited": len(visited_pages),
    }


def parse_jsonld(soup):
    products = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "Product":
                products.append(node)
            if "@graph" in node and isinstance(node["@graph"], list):
                for g in node["@graph"]:
                    if isinstance(g, dict) and g.get("@type") == "Product":
                        products.append(g)
    return products


def extract_price(soup):
    # 1) JSON-LD
    for p in parse_jsonld(soup):
        offer = p.get("offers") or {}
        price = None
        if isinstance(offer, dict):
            price = offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")
        elif isinstance(offer, list) and offer:
            o = offer[0]
            if isinstance(o, dict):
                price = o.get("price") or o.get("lowPrice") or o.get("highPrice")
        price = price or p.get("price") or (p.get("priceSpecification", {}) or {}).get("price")
        if price:
            rv = parse_rub_price(price)
            if rv != "Н/Д":
                return rv

    # 2) meta
    meta_price = soup.select_one('meta[itemprop="price"][content]')
    if meta_price and meta_price.get("content"):
        rv = parse_rub_price(meta_price["content"])
        if rv != "Н/Д":
            return rv

    og_price = soup.select_one('meta[property="product:price:amount"][content]')
    if og_price and og_price.get("content"):
        rv = parse_rub_price(og_price["content"])
        if rv != "Н/Д":
            return rv

    # 3) визуальные селекторы
    for sel in [
        '[data-qa*="price"]',
        '.price-current', '.current-price', '.product-price__current',
        '.product-price', '.price', '.Price__current', '.product__price',
        'span.price', 'div.price'
    ]:
        el = soup.select_one(sel)
        if el:
            num = parse_rub_price(el.get_text(" ", strip=True))
            if num != "Н/Д":
                return num

    # 4) общий фоллбэк
    any_price = soup.find(text=re.compile(r"\d[\d\s]{2,}.*(₽|руб|руб\.)", re.I))
    if any_price:
        rv = parse_rub_price(any_price)
        if rv != "Н/Д":
            return rv
    return "Н/Д"


def extract_article(soup):
    # JSON-LD
    for p in parse_jsonld(soup):
        sku = p.get("sku") or p.get("mpn")
        if sku:
            return str(sku).strip()
    # Явные подписи
    val = find_value_by_labels(soup, ["Артикул", "Код товара", "Модель", "SKU", "Код"])
    return val or "Н/Д"


def expand_tx_aliases(tx):
    if not tx:
        return []
    t = normalize(tx)
    aliases = [tx]  # оригинал тоже проверяем
    # Мощность
    if "мощност" in t:
        aliases += ["Мощность", "Потребляемая мощность", "Номинальная мощность", "Мощность двигателя"]
    # Скорость / обороты
    if "скорост" in t or "обмин" in t or "rpm" in t or "обор" in t:
        aliases += ["Скорость вращения", "Частота вращения", "Обороты", "Обороты холостого хода", "Скорость холостого хода"]
    # Энергия удара
    if "энерг" in t and "удар" in t:
        aliases += ["Энергия удара", "Сила удара"]
    # Частота ударов
    if "частота" in t and "удар" in t:
        aliases += ["Число ударов", "Частота ударов"]
    # АКБ
    if "напряжен" in t:
        aliases += ["Напряжение", "Напряжение аккумулятора"]
    if "емкост" in t or "ёмкост" in t:
        aliases += ["Емкость аккумулятора", "Ёмкость аккумулятора"]

    # dedup
    seen, res = set(), []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            res.append(a)
    return res


def find_value_by_labels(soup, labels):
    # labels — список «что ищем»; матчим по подстроке (normalized)
    norm_labels = [normalize(l) for l in labels if l]
    if not norm_labels:
        return None

    def match_key(k):
        nk = normalize(k)
        return any(nl in nk or nk in nl for nl in norm_labels)

    # Таблицы
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = cells[0].get_text(" ", strip=True)
            if match_key(key):
                return cells[1].get_text(" ", strip=True)

    # dl dt/dd
    for dt in soup.select("dl dt"):
        key = dt.get_text(" ", strip=True)
        if match_key(key):
            dd = dt.find_next("dd")
            if dd:
                return dd.get_text(" ", strip=True)

    # Контейнеры характеристик
    for container in soup.select(".characteristics, .props, .product-props, .product-attrs, .char, .chars, .properties, .product-properties, .product__chars, .product-specs"):
        for row in container.select("div, li, p"):
            spans = row.find_all("span")
            if len(spans) >= 2:
                key = spans[0].get_text(" ", strip=True)
                if match_key(key):
                    return spans[1].get_text(" ", strip=True)
            key_el = row.find(["b", "strong"])
            if key_el and match_key(key_el.get_text(" ", strip=True)):
                key_el.extract()
                return row.get_text(" ", strip=True)

    # Фоллбэк: "Ключ: Значение" в тексте
    text = soup.get_text("\n", strip=True)
    for lab in labels:
        lab_clean = re.sub(r"\s*KATEX_INLINE_OPEN.*?KATEX_INLINE_CLOSE\s*", "", lab).strip()
        if not lab_clean:
            continue
        rx = re.compile(rf"{re.escape(lab_clean)}\s*[:\-–]\s*([^\n\r;|]+)", re.I)
        m = rx.search(text)
        if m:
            return m.group(1).strip()

    return None


def build_props_dict(soup):
    props = {}

    # A) JSON-LD additionalProperty (PropertyValue)
    for p in parse_jsonld(soup):
        addp = p.get("additionalProperty") or p.get("additionalProperties")
        if isinstance(addp, list):
            for it in addp:
                if not isinstance(it, dict):
                    continue
                key = it.get("name") or it.get("propertyID")
                val = it.get("value") or it.get("valueReference") or it.get("propertyValue")
                if key and val:
                    props[normalize(key)] = str(val).strip()

    # B) Microdata/LD propertyValue
    for pv in soup.select('[itemprop="additionalProperty"], [itemtype*="PropertyValue"]'):
        key_el = pv.select_one('[itemprop="name"]')
        val_el = pv.select_one('[itemprop="value"]')
        if key_el and val_el:
            key = key_el.get_text(" ", strip=True)
            val = val_el.get_text(" ", strip=True)
            if key and val:
                props[normalize(key)] = val

    # C) data-qa name/value (частая React-вёрстка)
    name_nodes = soup.select('[data-qa*="char"][data-qa*="name"], [data-qa*="spec"][data-qa*="name"], [data-qa*="param"][data-qa*="name"], [data-qa*="character"][data-qa*="name"]')
    for name_el in name_nodes:
        key = name_el.get_text(" ", strip=True)
        if not key:
            continue
        row = name_el.parent
        val_el = row.select_one('[data-qa*="value"]')
        if not val_el:
            # второй вариант: другой соседний span/div
            candidates = [x for x in row.find_all(["span", "div"], recursive=False) if x is not name_el]
            for c in candidates:
                text = c.get_text(" ", strip=True)
                if text and normalize(text) != normalize(key):
                    val_el = c
                    break
        if val_el:
            val = val_el.get_text(" ", strip=True)
            if val:
                props[normalize(key)] = val

    # D) Таблицы
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = cells[0].get_text(" ", strip=True)
            val = cells[1].get_text(" ", strip=True)
            if key and val:
                props[normalize(key)] = val

    # E) dl dt/dd
    for dt in soup.select("dl dt"):
        dd = dt.find_next("dd")
        if dd:
            key = dt.get_text(" ", strip=True)
            val = dd.get_text(" ", strip=True)
            if key and val:
                props[normalize(key)] = val

    # F) “две колонки” и “Ключ: Значение”
    for row in soup.select("li, p, div"):
        children = [ch for ch in row.find_all(["div", "span"], recursive=False)]
        if len(children) == 2:
            k = children[0].get_text(" ", strip=True)
            v = children[1].get_text(" ", strip=True)
            if k and v and len(k) <= 60 and len(v) <= 200:
                props[normalize(k)] = v
                continue
        t = row.get_text(" ", strip=True)
        if 5 <= len(t) <= 220 and (":" in t or "—" in t or "-" in t):
            m = re.match(r"\s*([^:–—-]{2,60})\s*[:–—-]\s*(.{1,160})", t)
            if m:
                k = m.group(1).strip()
                v = m.group(2).strip()
                if k and v:
                    props[normalize(k)] = v

    return props


async def open_stocks_modal(page):
    """
    Пытаемся открыть модалку "Наличие в магазинах".
    Селекторы расширены, плюс JS-клик на случай кликабельных вложенных элементов.
    """
    selectors = [
        'button[data-qa="title-interactive-button"]',
        '[data-qa="title-interactive-button"]',
        'button:has([data-qa="title-interactive-stocks-text"])',
        '[data-qa="title-interactive-stocks-text"]',
        '[data-qa*="stocks-text"]',
        'button:has-text("Наличие")',
        'button:has-text("магазин")',
        'button:has-text("В наличии")',
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.scroll_into_view_if_needed()
                try:
                    await el.click(timeout=2000)
                except:
                    try:
                        await page.evaluate("(el) => el.click()", el)
                    except:
                        pass
                try:
                    await page.wait_for_selector('[data-qa="stocks-in-stores-modal"]', timeout=5000)
                    return True
                except:
                    continue
        except:
            continue

    # Фоллбэк: клик по тексту
    try:
        clicked = await page.evaluate("""() => {
            const texts = ['Наличие в магазинах', 'В наличии в', 'Наличие'];
            const nodes = document.querySelectorAll('button, [role="button"], [data-qa], span, div, a');
            for (const el of nodes) {
                const t = (el.textContent || '').trim();
                if (!t) continue;
                if (texts.some(x => t.includes(x))) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            await page.wait_for_selector('[data-qa="stocks-in-stores-modal"]', timeout=5000)
            return True
    except:
        pass
    return False


async def scroll_modal_to_end(page):
    # Скроллим контейнер модалки, если список длинный
    container_sel = '[data-qa="stocks-in-stores-modal"] [data-testid="drawer-content"]'
    try:
        await page.wait_for_selector(container_sel, timeout=3000)
    except:
        container_sel = '[data-qa="stocks-in-stores-modal"]'
    last_h = -1
    for _ in range(20):
        try:
            h = await page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (!el) return 0;
                const target = el;
                const sh = target.scrollHeight || 0;
                target.scrollTop = sh;
                return sh;
            }""", container_sel)
        except:
            h = 0
        await page.wait_for_timeout(300)
        if h == last_h:
            break
        last_h = h


async def extract_stock_units(page, soup):
    """
    Открывает модалку "Наличие в магазинах" и суммирует все количества "В наличии N шт."
    Возвращает строку с числом или None, если не удалось.
    """
    try:
        opened = await open_stocks_modal(page)
        if not opened:
            return None
        try:
            await page.wait_for_selector('[data-qa="stocks-in-stores-modal"]', timeout=5000)
            await page.wait_for_selector('[data-qa="modal-store-item-in-stock-text"]', timeout=6000)
        except:
            pass

        # прокрутим модалку, чтобы подгрузились все магазины
        await scroll_modal_to_end(page)

        items = await page.query_selector_all('[data-qa="stocks-in-stores-modal"] [data-qa="modal-store-item-in-stock-text"]')
        total = 0
        for it in items:
            try:
                t = await it.inner_text()
            except:
                t = ""
            # "В наличии 11 шт." / "Нет в наличии"
            m = re.search(r"(\d+)\s*(?:шт|штук)\b", t, re.I)
            if m:
                total += int(m.group(1))

        # Закрыть модалку
        for sel in [
            '[data-qa="stocks-in-stores-modal"] button:has-text("Закрыть")',
            '[data-testid="drawer-header-back"]',
            '[data-qa="stocks-in-stores-modal"] button[aria-label="назад"]',
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click(timeout=1200)
                    break
            except:
                continue
        try:
            await page.wait_for_selector('[data-qa="stocks-in-stores-modal"]', state="hidden", timeout=3000)
        except:
            pass

        return str(total)
    except:
        return None


def value_for_tx(props, soup, tx):
    if not tx:
        return "Н/Д"
    key = normalize(tx)

    # 1) точное
    val = props.get(key)
    if val:
        return val

    # 2) подстрочное совпадение
    for k, v in props.items():
        if key and (key in k or k in key):
            return v

    # 3) синонимы + структурный поиск
    aliases = expand_tx_aliases(tx)
    val = find_value_by_labels(soup, aliases if aliases else [tx])
    if val:
        return val

    # 4) похожесть
    if props:
        best = difflib.get_close_matches(key, props.keys(), n=1, cutoff=0.6)
        if best:
            return props[best[0]]

    return "Н/Д"


async def save_debug(page, tag):
    try:
        html_path = os.path.join(DEBUG_DIR, f"lemanapro_{tag}.html")
        png_path = os.path.join(DEBUG_DIR, f"lemanapro_{tag}.png")
        html = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            await page.screenshot(path=png_path, full_page=True)
        except:
            pass
        return html_path, png_path
    except:
        return None, None


async def extract_data(page, url, tx1, tx2):
    await goto_with_retries(page, url, tries=3, tag="product")
    await maybe_pass_challenge(page)

    html = await page.content()
    soup = BeautifulSoup(html, "lxml")

    # Иногда характеристики скрыты под кнопкой
    await safe_click_button(page, [
        'button:has-text("Все характеристики")',
        'button:has-text("Показать все характеристики")',
    ], timeout=1500)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")

    # Название
    name_el = soup.select_one("h1, .product-title, .ProductTitle, .card-title")
    name = name_el.get_text(" ", strip=True) if name_el else "Н/Д"

    # Цена / Артикул
    price = extract_price(soup)
    article = extract_article(soup)

    # Остаток: пытаемся посчитать суммарное количество из модалки
    stock_units = await extract_stock_units(page, soup)
    if stock_units is None:
        # фоллбэк: вернём общий статус, если не удалось открыть модалку
        stock_el = soup.select_one('[data-qa="title-interactive-stocks-text"], [data-qa*="stocks-text"]')
        stock_units = "Н/Д"
        if stock_el:
            stock_units = stock_el.get_text(" ", strip=True) or "Н/Д"

    main_info = {
        "Ссылка": url,
        "Артикул": article,
        "Название": name,
        "Цена": price,
        "Остаток": stock_units,  # число штук (строкой) либо фоллбэк-текст/Н/Д
    }

    # Характеристики
    props = build_props_dict(soup)
    main_info[f"ТХ1_{tx1}"] = value_for_tx(props, soup, tx1)
    main_info[f"ТХ2_{tx2}"] = value_for_tx(props, soup, tx2)

    return main_info


async def scrape_with_engine(p, engine, url, tx1, tx2, debug_messages):
    context = None
    browser = None
    try:
        if engine == "chromium":
            profile_dir = os.path.join(DEBUG_DIR, "plw-lemanapro-chromium")
            context = await p.chromium.launch_persistent_context(
                profile_dir,
                headless=True,
                user_agent=REAL_UA,
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1366, "height": 820},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                geolocation={"longitude": 37.6173, "latitude": 55.7558},
                permissions=["geolocation"],
                args=["--lang=ru-RU,ru", "--disable-blink-features=AutomationControlled"],
            )
        elif engine == "firefox":
            browser = await p.firefox.launch(headless=True)
            context = await browser.new_context(
                user_agent=REAL_UA,
                viewport={"width": 1366, "height": 820},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )
        else:
            browser = await p.webkit.launch(headless=True)
            context = await browser.new_context(
                user_agent=REAL_UA,
                viewport={"width": 1366, "height": 820},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )

        await context.set_extra_http_headers(COMMON_HEADERS)
        page = await context.new_page()
        await stealth_async(page)

        path = urlparse(url).path
        if path.startswith("/product/"):
            data = await extract_data(page, url, tx1, tx2)
            return [data]

        links, meta = await collect_links(page, url)
        if not links:
            title = meta.get("title")
            blocked = meta.get("blocked")
            html_path, png_path = await save_debug(page, f"category_{engine}")
            msg = f"{engine}: 0 товарных ссылок. blocked={blocked}, title='{title}'. Снимки: {html_path}, {png_path}"
            debug_messages.append(msg)
            raise Exception(msg)

        results = []
        per_link_errors = []

        # Парсим все карточки без агрессивного префильтра
        for i, link in enumerate(links, 1):
            try:
                data = await extract_data(page, link, tx1, tx2)
                results.append(data)
            except Exception as e:
                per_link_errors.append((link, str(e)[:200]))
                continue

        if not results:
            try:
                await goto_with_retries(page, links[0], tries=2, tag="product_debug")
                await save_debug(page, f"product_{engine}")
            except:
                pass
            err_preview = "; ".join([f"{i+1}) {u} -> {msg}" for i, (u, msg) in enumerate(per_link_errors[:5])])
            raise Exception(f"{engine}: получили {len(links)} ссылок, но 0 результатов. Примеры ошибок: {err_preview}")

        return results

    finally:
        try:
            if context:
                await context.close()
        except:
            pass
        try:
            if browser:
                await browser.close()
        except:
            pass


@register_parser("lemanapro", "Лемана ПРО")
async def run_parser(url, tx1, tx2):
    """
    Универсальный парсер:
    - Любая категория (берём все /product/ ссылки с пагинации ?page=...) или одна карточка (/product/...)
    - Любые tx1/tx2
    - Остаток: сумма штук по всем магазинам из модального окна (если доступно)
    """
    debug_messages = []
    async with async_playwright() as p:
        try:
            res = await scrape_with_engine(p, "chromium", url, tx1, tx2, debug_messages)
            if res:
                return res
        except Exception as e:
            debug_messages.append(f"chromium fail: {str(e)}")

        try:
            res = await scrape_with_engine(p, "firefox", url, tx1, tx2, debug_messages)
            if res:
                return res
        except Exception as e:
            debug_messages.append(f"firefox fail: {str(e)}")

        try:
            res = await scrape_with_engine(p, "webkit", url, tx1, tx2, debug_messages)
            if res:
                return res
        except Exception as e:
            debug_messages.append(f"webkit fail: {str(e)}")

    raise Exception("Lemana: 0 items. " + " | ".join(debug_messages))