from django.contrib.auth.models import AbstractUser
from django.db import models
class CustomUser(AbstractUser):
    
    def __str__(self):
        return self.username
    


class Destination(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField()
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100, blank=True, null=True)

    image = models.ImageField(upload_to='destinations/', blank=True, null=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Estimated cost or package price"
    )

    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
