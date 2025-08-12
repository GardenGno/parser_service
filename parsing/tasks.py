# parsing/tasks.py
import asyncio
from .models import Request, Result
from .parsers import get_parser

def run_parser_task(request_id):
    req = Request.objects.select_related("shop").get(id=request_id)
    parser_func = get_parser(req.shop.parser_key)

    if not parser_func:
        req.status = "error"
        req.error_message = f"Parser for shop '{req.shop.parser_key}' not found"
        req.save()
        return

    try:
        results = asyncio.run(
            parser_func(req.url, req.params.get("tx1"), req.params.get("tx2"))
        )
        if not results:
            raise RuntimeError("Parser returned 0 results (blocked by site or no items found)")

        for res in results:
            Result.objects.create(
                request=req,
                url=res.get("Ссылка"),
                article=res.get("Артикул"),
                name=res.get("Название"),
                price=res.get("Цена"),
                stock=res.get("Остаток"),
                tx1=res.get(f"ТХ1_{req.params.get('tx1')}"),
                tx2=res.get(f"ТХ2_{req.params.get('tx2')}"),
            )
        req.status = "done"
        req.error_message = None
    except Exception as e:
        req.status = "error"
        req.error_message = str(e)
    req.save()
