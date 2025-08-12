from rest_framework import serializers
from .models import Request, Shop

class RequestSerializer(serializers.ModelSerializer):

    url = serializers.URLField(max_length=10000)
    class Meta:
        model = Request
        fields = "__all__"