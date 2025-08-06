from django.db import models
from django.db.models import JSONField

# Create your models here.


class Request(models.Model):
    user_id = models.IntegerField()
    shop_name = models.CharField(max_length=255)
    url = models.URLField()
    params = JSONField()  # {'category': ..., 'tx1': ..., 'tx2': ...}
    status = models.CharField(max_length=32, default="pending")  # pending, done, error
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parsing_requests"


class Result(models.Model):
    request = models.ForeignKey(
        Request, on_delete=models.CASCADE, related_name="results"
    )
    url = models.URLField(null=True, blank=True)
    article = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    price = models.CharField(max_length=50, blank=True, null=True)
    stock = models.CharField(max_length=50, blank=True, null=True)
    tx1 = models.CharField(max_length=255, blank=True, null=True)
    tx2 = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parsing_results"
