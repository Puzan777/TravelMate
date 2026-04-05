from django.contrib.auth.models import AbstractUser
from django.core.files.storage import default_storage
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        VENDOR = 'VENDOR', 'Vendor'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    favorite_packages = models.ManyToManyField(
        'Package',
        blank=True,
        related_name='favorited_by'
    )

    @property
    def is_vendor(self):
        return self.role == self.Role.VENDOR
    
    def __str__(self):
        return self.username
    


class Destination(models.Model):
    """Represents a country/region where packages are available."""
    name = models.CharField(max_length=150, unique=True, help_text="Country name (e.g., Nepal, Thailand)")
    short_description = models.TextField(blank=True, help_text="Short text for destination cards")
    hero_image = models.ImageField(upload_to='destinations/', blank=True, null=True)
    best_season = models.CharField(max_length=120, blank=True, help_text="Example: Mar-May, Sep-Nov")
    visa_info = models.CharField(max_length=255, blank=True)
    safety_note = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class Package(models.Model):
    class Category(models.TextChoices):
        LUXURY = 'LUXURY', 'Luxury'
        TREKKING = 'TREKKING', 'Trekking'
        HELI = 'HELI', 'Heli'

    title = models.CharField(max_length=200)
    vendor = models.ForeignKey(
        'vendor.VendorProfile',
        on_delete=models.PROTECT,
        related_name='packages',
    )
    # optional slug for pretty URLs; generated automatically if blank
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    image = models.ImageField(upload_to='packages/')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        help_text='Package rating from 0.0 to 5.0'
    )

    # single description field rather than short/full
    description = models.TextField()

    # link to Destination (country selection - optional for backwards compatibility)
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT, blank=True, null=True, related_name='packages')
    region = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=120, blank=True)
    best_season = models.CharField(max_length=120, blank=True)

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
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        help_text='Admin approval status. Only approved packages are shown on the site.',
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text='Reason provided by admin if the package is rejected. Vendor will see this.',
    )

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


class PackageItinerary(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='itinerary_entries')
    day_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    activities = models.TextField(blank=True)
    max_elevation = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    distance = models.CharField(max_length=100, blank=True)
    difficulty_level = models.CharField(max_length=100, blank=True)
    meals_included = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ['day_number']
        constraints = [
            models.UniqueConstraint(fields=['package', 'day_number'], name='unique_package_day_number'),
        ]

    def __str__(self):
        return f"{self.package.title} - Day {self.day_number}"


class PackageImage(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='packages/')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"{self.package.title} image"

    def clean(self):
        sibling_qs = PackageImage.objects.filter(package_id=self.package_id).exclude(pk=self.pk)
        if self.is_primary and sibling_qs.filter(is_primary=True).exists():
            raise ValidationError({'is_primary': 'Only one package image can be primary.'})
        if not self.is_primary and sibling_qs.exists() and not sibling_qs.filter(is_primary=True).exists():
            raise ValidationError({'is_primary': 'At least one package image must be primary.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ActivityCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Activity Category'
        verbose_name_plural = 'Activity Categories'

    def __str__(self):
        return self.name


class Activity(models.Model):
    class DifficultyLevel(models.TextChoices):
        EASY = 'easy', 'Easy'
        MODERATE = 'moderate', 'Moderate'
        HARD = 'hard', 'Hard'

    vendor = models.ForeignKey('vendor.VendorProfile', on_delete=models.CASCADE, related_name='activities')
    category = models.ForeignKey(ActivityCategory, on_delete=models.PROTECT, related_name='activities')
    name = models.CharField(max_length=150)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_group_size = models.PositiveIntegerField(blank=True, null=True)
    equipment_provided = models.TextField(blank=True)
    safety_notes = models.TextField(blank=True)
    duration = models.CharField(max_length=100)
    difficulty_level = models.CharField(max_length=20, choices=DifficultyLevel.choices)
    min_age = models.PositiveIntegerField(blank=True, null=True)
    max_weight = models.PositiveIntegerField(blank=True, null=True)
    min_weight = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        help_text='Admin approval status. Only approved activities are shown on the site.',
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text='Reason provided by admin if the activity is rejected. Vendor will see this.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['vendor', 'name'], name='unique_vendor_activity_name'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.min_weight is not None and self.max_weight is not None and self.min_weight > self.max_weight:
            errors['min_weight'] = 'Minimum weight cannot be greater than maximum weight.'
        if self.category_id and not self.category.is_active:
            errors['category'] = 'Please choose an active category.'
        if errors:
            raise ValidationError(errors)


class ActivityImage(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='activities/')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"{self.activity.name} image"

    def clean(self):
        sibling_qs = ActivityImage.objects.filter(activity_id=self.activity_id).exclude(pk=self.pk)
        if self.is_primary and sibling_qs.filter(is_primary=True).exists():
            raise ValidationError({'is_primary': 'Only one activity image can be primary.'})
        if not self.is_primary and sibling_qs.exists() and not sibling_qs.filter(is_primary=True).exists():
            raise ValidationError({'is_primary': 'At least one activity image must be primary.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class HotSale(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='hot_sale_entries', null=True, blank=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='hot_sale_entries', null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    note = models.TextField(blank=True, help_text='Optional note shown only on the hot sale page.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Hot Sale'
        verbose_name_plural = 'Hot Sales'
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(package__isnull=False) & models.Q(activity__isnull=True))
                    | (models.Q(package__isnull=True) & models.Q(activity__isnull=False))
                ),
                name='hotsale_exactly_one_target',
            ),
        ]

    def __str__(self):
        return f"{self.target_name} - {self.sale_price}"

    @property
    def target_name(self):
        if self.package_id:
            return self.package.title
        if self.activity_id:
            return self.activity.name
        return 'Unknown Offer'

    @property
    def target_type(self):
        if self.package_id:
            return 'Package'
        if self.activity_id:
            return 'Activity'
        return 'Offer'

    @property
    def original_price(self):
        if self.package_id:
            return self.package.price
        if self.activity_id:
            return self.activity.price
        return None

    @property
    def activity_primary_image(self):
        if not self.activity_id:
            return None
        return self.activity.images.first()

    def clean(self):
        if bool(self.package_id) == bool(self.activity_id):
            raise ValidationError('Select either a package or an activity for the hot sale.')

        original_price = self.original_price
        if original_price is not None and self.sale_price is not None and self.sale_price >= original_price:
            raise ValidationError({
                'sale_price': 'Hot sale price must be lower than the original price.'
            })

    @property
    def savings_amount(self):
        original_price = self.original_price
        if original_price is None:
            return 0
        return original_price - self.sale_price


class Booking(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    travel_date = models.DateField()
    number_of_people = models.PositiveIntegerField(default=1)
    pickup_location = models.CharField(max_length=150, blank=True)
    nationality = models.CharField(max_length=80)
    emergency_contact = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.package.title} - {self.full_name} - {self.travel_date}"


class Inquiry(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='inquiries')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='inquiries')
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField()
    admin_reply = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if self.admin_reply and self.replied_at is None:
            self.replied_at = timezone.now()
        if not self.admin_reply:
            self.replied_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Inquiry: {self.package.title} ({self.full_name})"


def _normalize_single_primary(sender, parent_fk_name, parent_id):
    if parent_id is None:
        return

    images = sender.objects.filter(**{f'{parent_fk_name}_id': parent_id}).order_by('created_at', 'pk')
    if not images.exists():
        return

    primary_ids = list(images.filter(is_primary=True).values_list('pk', flat=True))
    if len(primary_ids) == 1:
        return

    if len(primary_ids) == 0:
        first_image = images.first()
        if first_image is not None:
            images.filter(pk=first_image.pk).update(is_primary=True)
        return

    keep_id = primary_ids[0]
    images.exclude(pk=keep_id).filter(is_primary=True).update(is_primary=False)


def _delete_file_if_unreferenced(file_name, checks):
    if not file_name:
        return

    for check in checks:
        if check().exists():
            return

    if default_storage.exists(file_name):
        default_storage.delete(file_name)


@receiver(post_save, sender=ActivityImage)
def _activity_image_post_save(sender, instance, **kwargs):
    _normalize_single_primary(ActivityImage, 'activity', instance.activity_id)


@receiver(post_delete, sender=ActivityImage)
def _activity_image_post_delete(sender, instance, **kwargs):
    file_name = getattr(instance.image, 'name', None)
    _delete_file_if_unreferenced(
        file_name,
        checks=[
            lambda: ActivityImage.objects.filter(image=file_name),
        ],
    )
    _normalize_single_primary(ActivityImage, 'activity', instance.activity_id)


@receiver(post_save, sender=PackageImage)
def _package_image_post_save(sender, instance, **kwargs):
    _normalize_single_primary(PackageImage, 'package', instance.package_id)


@receiver(post_delete, sender=PackageImage)
def _package_image_post_delete(sender, instance, **kwargs):
    file_name = getattr(instance.image, 'name', None)
    _delete_file_if_unreferenced(
        file_name,
        checks=[
            lambda: PackageImage.objects.filter(image=file_name),
            lambda: Package.objects.filter(image=file_name),
        ],
    )
    _normalize_single_primary(PackageImage, 'package', instance.package_id)


@receiver(pre_save, sender=Package)
def _package_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_image_name = None
        return

    try:
        old_package = sender.objects.only('image').get(pk=instance.pk)
        instance._old_image_name = old_package.image.name
    except sender.DoesNotExist:
        instance._old_image_name = None


@receiver(post_save, sender=Package)
def _package_post_save(sender, instance, **kwargs):
    old_name = getattr(instance, '_old_image_name', None)
    new_name = getattr(instance.image, 'name', None)

    if old_name and old_name != new_name:
        _delete_file_if_unreferenced(
            old_name,
            checks=[
                lambda: Package.objects.filter(image=old_name),
                lambda: PackageImage.objects.filter(image=old_name),
            ],
        )


@receiver(post_delete, sender=Package)
def _package_post_delete(sender, instance, **kwargs):
    file_name = getattr(instance.image, 'name', None)
    _delete_file_if_unreferenced(
        file_name,
        checks=[
            lambda: Package.objects.filter(image=file_name),
            lambda: PackageImage.objects.filter(image=file_name),
        ],
    )
