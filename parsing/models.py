from django.db import models
from django.db.models import JSONField

# Create your models here.


class Shop(models.Model):
    name = models.CharField(max_length=255, unique=True)
    parser_key = models.CharField(max_length=128, unique=True, db_index=True)

    class Meta:
        db_table = "shops"

    def __str__(self):
        return self.name



class Request(models.Model):
    user_id = models.IntegerField()
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="requests")
    url = models.TextField()
    params = JSONField()  # {'category': ..., 'tx1': ..., 'tx2': ...}
    status = models.CharField(max_length=32, default="pending")  # pending, done, error
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parsing_requests"


class Result(models.Model):
    request = models.ForeignKey(
        Request, on_delete=models.CASCADE, related_name="results"
    )
    url = models.TextField(null=True, blank=True)
    article = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    price = models.CharField(max_length=50, blank=True, null=True)
    stock = models.CharField(max_length=50, blank=True, null=True)
    tx1 = models.CharField(max_length=255, blank=True, null=True)
    tx2 = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parsing_results"



