from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse


class CustomUser(AbstractUser):
    
    def __str__(self):
        return self.username
    


class Destination(models.Model):
    """Represents a country/region where packages are available."""
    name = models.CharField(max_length=150, unique=True, help_text="Country name (e.g., Nepal, Thailand)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Package(models.Model):
    class Category(models.TextChoices):
        LUXURY = 'LUXURY', 'Luxury'
        TREKKING = 'TREKKING', 'Trekking'
        HELI = 'HELI', 'Heli'

    title = models.CharField(max_length=200)
    # optional slug for pretty URLs; generated automatically if blank
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    image = models.ImageField(upload_to='packages/')
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # single description field rather than short/full
    description = models.TextField()

    # link to Destination (country selection - optional for backwards compatibility)
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT, blank=True, null=True, related_name='packages')

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

    def save(self, *args, **kwargs):
        # auto-populate slug from title if not specified
        from django.utils.text import slugify

        if not self.slug:
            base = slugify(self.title)
            slug = base
            counter = 1
            # ensure uniqueness across existing packages
            while Package.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('package_detail', args=[self.slug])
