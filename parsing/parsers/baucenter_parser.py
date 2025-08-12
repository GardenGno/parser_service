import re
from . import register_parser
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


def normalize(text):
    return re.sub(r"\W+", "", str(text).lower()).strip()


async def extract_links(page, url):
    await page.goto(url, timeout=60000)
    try:
        await page.locator('button:has-text("Да")').click(timeout=3000)
        await page.wait_for_timeout(1500)
        await page.reload(timeout=60000)
        await page.wait_for_timeout(1500)
    except:
        pass

    await page.wait_for_selector("p:has-text('товар')", timeout=10000)
    total_text = await page.inner_text("p:has-text('товар')")
    total = int(re.search(r"\d+", total_text).group())

    last_count = 0
    for _ in range(15):
        cards = await page.query_selector_all("[data-product-card-id]")
        if len(cards) == last_count:
            break
        last_count = len(cards)
        show_more = await page.query_selector('button:has-text("Показать ещё")')
        if not show_more:
            break
        await show_more.scroll_into_view_if_needed()
        await show_more.click()
        await page.wait_for_timeout(3000)

    links = set()
    cards = await page.query_selector_all("[data-product-card-id]")
    for card in cards:
        a = await card.query_selector('a[href^="/product/"]')
        if a:
            href = await a.get_attribute("href")
            if href:
                links.add(urljoin("https://baucenter.ru", href))

    if abs(len(links) - total) > 2:
        await page.wait_for_timeout(3000)
        cards = await page.query_selector_all("[data-product-card-id]")
        for card in cards:
            a = await card.query_selector('a[href^="/product/"]')
            if a:
                href = await a.get_attribute("href")
                if href:
                    links.add(urljoin("https://baucenter.ru", href))

    if abs(len(links) - total) > 2:
        raise Exception(f"❌ Ссылок: {len(links)} ≠ товаров: {total}")

    return list(links), total


async def extract_data(page, url, tx1, tx2):
    await page.goto(url, timeout=60000)
    await page.wait_for_timeout(2000)
    soup = BeautifulSoup(await page.content(), "lxml")

    def extract_number(text):
        digits = re.findall(r"\d+", text.replace(" ", ""))
        return int("".join(digits)) if digits else "Н/Д"

    name_elem = soup.select_one("h1")
    name = name_elem.get_text(strip=True) if name_elem else "Н/Д"

    price_elem = soup.select_one('span[class*="MainPrice"]')
    price = extract_number(price_elem.get_text()) if price_elem else "Н/Д"

    article_elem = soup.select_one('span[class*="CopiedTypography"] span')
    article = article_elem.get_text(strip=True) if article_elem else "Н/Д"

    stock = "Н/Д"
    try:
        stock_p = soup.select_one(
            "ul[class*='AvailabilitiesList'] p:-soup-contains('шт')"
        )
        if stock_p:
            stock = re.sub(r"\D+", "", stock_p.get_text(strip=True)) or "Н/Д"
    except:
        pass

    main_info = {
        "Ссылка": url,
        "Артикул": article,
        "Название": name,
        "Цена": price,
        "Остаток": stock,
    }

    props = soup.select('div[class^="styled__ProductCardProperty-sc-"]')
    for prop in props:
        key_el = prop.select_one("span")
        val_el = prop.select_one("a, p, div[class*='ProductCardPropertyValue']")
        if key_el:
            key = key_el.get_text(strip=True)
            candidates = [
                el.get_text(strip=True)
                for el in prop.select(
                    "a, p, div[class*='ProductCardPropertyValue'], span"
                )
                if el.get_text(strip=True) != key
            ]
            if candidates:
                value = candidates[0]
                if normalize(key) == normalize(tx1):
                    main_info[f"ТХ1_{tx1}"] = value
                if normalize(key) == normalize(tx2):
                    main_info[f"ТХ2_{tx2}"] = value

    if f"ТХ1_{tx1}" not in main_info:
        main_info[f"ТХ1_{tx1}"] = "Н/Д"
    if f"ТХ2_{tx2}" not in main_info:
        main_info[f"ТХ2_{tx2}"] = "Н/Д"

    return main_info

@register_parser("baucenter", "Бауцентр")
async def run_parser(url, tx1, tx2):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            locale="ru-RU",
            viewport={"width": 1280, "height": 800},
            geolocation={"longitude": 37.6173, "latitude": 55.7558},
            permissions=["geolocation"],
        )
        page = await context.new_page()
        links, _ = await extract_links(page, url)
        for link in links:
            try:
                data = await extract_data(page, link, tx1, tx2)
                results.append(data)
            except Exception as e:
                continue
        await browser.close()
    return results
