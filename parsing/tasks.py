import asyncio
from .models import Request, Result

# Импортируй все парсеры
from .parsers import baucenter_parser

PARSER_MAP = {
    "Бауцентр": baucenter_parser.run_parser,
    # и т.д.
}

def run_parser_task(request_id):
    request = Request.objects.get(id=request_id)
    params = request.params
    shop_name = request.shop_name

    parser_function = PARSER_MAP.get(shop_name)
    if not parser_function:
        print(f"Parser for shop '{shop_name}' not found!")
        request.status = "error"
        request.save()
        return

    try:
        results = asyncio.run(
            parser_function(
                url=request.url, tx1=params.get("tx1"), tx2=params.get("tx2")
            )
        )
        for res in results:
            Result.objects.create(
                request=request,
                url=res.get("Ссылка"),
                article=res.get("Артикул"),
                name=res.get("Название"),
                price=res.get("Цена"),
                stock=res.get("Остаток"),
                tx1=res.get(f"ТХ1_{params.get('tx1')}"),
                tx2=res.get(f"ТХ2_{params.get('tx2')}"),
            )
        request.status = "done"
        request.save()
    except Exception as e:
        print(f"Parser error: {e}")
        request.status = "error"
        request.save()