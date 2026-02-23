from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse


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


class Package(models.Model):
    class Category(models.TextChoices):
        LUXURY = 'LUXURY', 'Luxury'
        TREKKING = 'TREKKING', 'Trekking'
        HELI = 'HELI', 'Heli'

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices)
    image = models.ImageField(upload_to='packages/')
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # single description field rather than short/full
    description = models.TextField()

    # link to Destination (optional)
    destination = models.ForeignKey(Destination, on_delete=models.SET_NULL, blank=True, null=True)

    duration = models.CharField(max_length=100)
    max_people = models.PositiveIntegerField(blank=True, null=True)
    trip_difficulty = models.CharField(max_length=100, blank=True, null=True)
    activity = models.CharField(max_length=100, blank=True, null=True)
    max_elevation = models.IntegerField(blank=True, null=True)
    accommodation = models.CharField(max_length=100, blank=True, null=True)
    meal = models.CharField(max_length=100, blank=True, null=True)
    vehicle = models.CharField(max_length=100, blank=True, null=True)

    major_highlights = models.TextField(blank=True, null=True)
    itinerary = models.TextField(blank=True, null=True)

    is_hot_sale = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Package'
        verbose_name_plural = 'Packages'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # detail view now uses primary key instead of slug
        return reverse('package_detail', args=[self.pk])
