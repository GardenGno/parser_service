# parsing/parsers/petrovich.py
import re
import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright

from . import register_parser

WORKERS = 4

def normalize(text):
    return re.sub(r"\W+", "", str(text).lower()).strip()

async def collect_product_links(page, list_url):
    await page.goto(list_url, timeout=60000)
    await page.wait_for_load_state("domcontentloaded")

    # Пытаемся закрыть/принять возможные модалки/куки
    try:
        await page.get_by_role("button", name=re.compile(r"да|принять|соглас", re.I)).click(timeout=2000)
        await page.wait_for_timeout(500)
    except:
        pass

    # Ждем появления товаров/списка
    await page.wait_for_selector('a[data-test="product-link"], [data-item-code]', timeout=30000)

    # Считать заявленное количество товаров (не критично)
    total_expected = None
    try:
        counter_text = await page.locator('[data-test="products-counter"]').inner_text()
        digits = re.findall(r"\d+", counter_text.replace("\xa0", ""))
        if digits:
            total_expected = int(digits[-1])
    except:
        pass

    # Собираем URL всех страниц пагинации
    page_urls = {list_url}
    try:
        paginator = await page.locator('[data-test="paginator-page-btn"]').all()
        for a in paginator:
            href = await a.get_attribute("href")
            if href:
                page_urls.add(urljoin(list_url, href))
    except:
        pass

    links = set()
    for purl in sorted(page_urls):
        await page.goto(purl, timeout=60000)
        await page.wait_for_selector('a[data-test="product-link"], [data-item-code]', timeout=30000)
        anchors = await page.locator('[data-item-code] >> a[data-test="product-link"], a[data-test="product-link"]').all()
        for a in anchors:
            try:
                href = await a.get_attribute("href")
                if href:
                    links.add(urljoin(purl, href))
            except:
                continue
        if total_expected and len(links) >= total_expected:
            break

    return list(links)

async def extract_product_info(page, product_url, tx1, tx2):
    await page.goto(product_url, timeout=60000)
    await page.wait_for_load_state("domcontentloaded")

    # Раскрыть блок характеристик, если есть
    try:
        await page.get_by_text("Полные характеристики", exact=False).first.click(timeout=2500)
        await page.wait_for_timeout(400)
    except:
        pass

    # Название
    name = "Н/Д"
    try:
        name = (await page.locator('h1[data-test="product-title"]').inner_text()).strip()
    except:
        pass

    # Цена
    price = "Н/Д"
    try:
        price_text = await page.locator('p[data-test="product-gold-price"]').first.inner_text()
        digits = re.sub(r"[^\d]", "", price_text or "")
        price = int(digits) if digits else "Н/Д"
    except:
        pass

    # Артикул
    article = "Н/Д"
    try:
        article = (await page.locator('li.data-item:has(.title:has-text("Артикул")) .value').first.inner_text()).strip()
    except:
        try:
            # альтернативные варианты
            article = (await page.locator('[data-test="product-code"], [data-test="product-sku"], [itemprop="sku"]').first.inner_text()).strip()
        except:
            pass

    # Остаток
    stock = "Н/Д"
    try:
        # пробуем вытащить из свойства с числом
        stock_candidate = await page.locator('li.data-item:has(.title:has-text("налич")), li.data-item:has(.title:has-text("склад")) .value').first.inner_text()
        digits = re.sub(r"[^\d]", "", stock_candidate or "")
        stock = digits if digits else "Н/Д"
    except:
        try:
            # простой фолбэк
            stock_candidate = await page.locator('div.value').first.inner_text()
            digits = re.sub(r"[^\d]", "", stock_candidate or "")
            stock = digits if digits else "Н/Д"
        except:
            pass

    # Характеристики для tx1/tx2
    tx1_val, tx2_val = None, None
    try:
        props = await page.locator('ul.product-properties-list li.data-item').all()
        for block in props:
            try:
                label = (await block.locator('.title').inner_text()).strip()
                value = (await block.locator('.value').inner_text()).strip()
                if tx1 and normalize(tx1) in normalize(label):
                    tx1_val = value
                if tx2 and normalize(tx2) in normalize(label):
                    tx2_val = value
            except:
                continue
    except:
        pass

    data = {
        "Ссылка": product_url,
        "Артикул": article,
        "Название": name,
        "Цена": price,
        "Остаток": stock,
    }
    if tx1:
        data[f"ТХ1_{tx1}"] = tx1_val if tx1_val else "Н/Д"
    if tx2:
        data[f"ТХ2_{tx2}"] = tx2_val if tx2_val else "Н/Д"

    return data

async def worker(name, context, queue, tx1, tx2, results):
    page = await context.new_page()
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            i, total, link = item
            try:
                res = await extract_product_info(page, link, tx1, tx2)
                results.append(res)
            except Exception as e:
                # Можно добавить логирование
                pass
            finally:
                queue.task_done()
    finally:
        await page.close()

@register_parser("petrovich", "Петрович")
async def run_parser(url, tx1, tx2):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ru-RU",
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        context.set_default_timeout(45000)
        context.set_default_navigation_timeout(60000)

        page = await context.new_page()
        product_links = await collect_product_links(page, url)
        await page.close()

        # Очередь и воркеры
        queue = asyncio.Queue()
        for i, link in enumerate(product_links, 1):
            await queue.put((i, len(product_links), link))

        n_workers = min(WORKERS, max(1, len(product_links)))
        workers = [asyncio.create_task(worker(f"W{idx+1}", context, queue, tx1, tx2, results))
                   for idx in range(n_workers)]

        await queue.join()
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)

        await browser.close()

    return results