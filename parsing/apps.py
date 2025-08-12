from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ParsingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parsing'

    def ready(self):
        # 1) Подтягиваем и регистрируем все парсеры
        from .parsers import autodiscover, PARSERS  # noqa
        autodiscover()

        # 2) После миграций создаём записи в shops
        def ensure_shops(sender, **kwargs):
            from .models import Shop
            for key, func in PARSERS.items():
                name = getattr(func, "_shop_name", key)
                Shop.objects.get_or_create(parser_key=key, defaults={"name": name})

        post_migrate.connect(ensure_shops, sender=self)
