import uuid
from django.db import models
from django.conf import settings


class UserToken(models.Model):
    TOKEN_TYPES = (('access', 'access'), ('refresh', 'refresh'))

    user_id = models.BigIntegerField(db_index=True)  
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    token_type = models.CharField(max_length=10, choices=TOKEN_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user_id} | {self.token_type} | revoked={self.revoked}"