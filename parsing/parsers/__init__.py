# parsing/parsers/__init__.py
import pkgutil
import importlib
from typing import Callable, Dict

PARSERS: Dict[str, Callable] = {}

def register_parser(key: str, shop_name: str):
    def decorator(func: Callable):
        PARSERS[key] = func
        func._shop_name = shop_name  # чтобы потом знать, какое имя записывать в Shop
        return func
    return decorator

def get_parser(key: str):
    return PARSERS.get(key)

def autodiscover():
    package = __name__
    for _, name, _ in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{package}.{name}")
