from django.db import models
from django.conf import settings


class ExternalUser(models.Model):
    id = models.BigIntegerField(primary_key=True, db_column='id')
    name = models.CharField(max_length=255, db_column='name')
    email = models.CharField(max_length=255, db_column='email')
    email_verified_at = models.DateTimeField(null=True, blank=True, db_column='email_verified_at')
    password = models.CharField(max_length=255, db_column='password')
    remember_token = models.CharField(max_length=100, null=True, blank=True, db_column='remember_token')
    created_at = models.DateTimeField(null=True, blank=True, db_column='created_at')
    updated_at = models.DateTimeField(null=True, blank=True, db_column='updated_at')

    # Чтобы DRF IsAuthenticated работал без падений
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    @property
    def is_active(self): return True

    def __str__(self):
        return f"{self.id} | {self.email}"

    class Meta:
        managed = False
        db_table = 'users'


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