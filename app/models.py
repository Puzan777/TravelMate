from django.contrib.auth.models import AbstractUser
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Avg
from django.db.models.signals import post_delete, post_save, pre_save
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


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
    favorite_activities = models.ManyToManyField(
        'Activity',
        blank=True,
        related_name='favorited_by_users'
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
    is_featured = models.BooleanField(default=False, help_text='Show this destination in the Top Destinations section on the homepage.')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def display_image(self):
        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('images')
        images = list(prefetched) if prefetched is not None else list(self.images.all())
        primary = next((img for img in images if img.is_primary), None)
        if primary is None and images:
            primary = images[0]
        if primary and primary.image:
            return primary.image
        return self.hero_image


class DestinationImage(models.Model):
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='destinations/')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"{self.destination.name} image"


class ApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class Package(models.Model):
    class Category(models.TextChoices):
        STANDARD = 'STANDARD', 'Standard Package'
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
    tour_type = models.CharField(max_length=100, blank=True, null=True)
    max_elevation = models.IntegerField(blank=True, null=True)
    accommodation = models.CharField(max_length=100, blank=True, null=True)
    meal = models.CharField(max_length=100, blank=True, null=True)
    vehicle = models.CharField(max_length=100, blank=True, null=True)

    major_highlights = models.TextField(blank=True, null=True)
    itinerary = models.TextField(blank=True, null=True)

    is_hot_sale = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False, help_text='Show this package in the Best Packages section on the homepage.')
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
    destination = models.ForeignKey(
        Destination,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='activities',
    )
    region = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=120, blank=True)
    best_season = models.CharField(max_length=120, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        help_text='Activity rating from 0.0 to 5.0'
    )
    max_group_size = models.PositiveIntegerField(blank=True, null=True)
    equipment_provided = models.TextField(blank=True)
    safety_notes = models.TextField(blank=True)
    duration = models.CharField(max_length=100)
    difficulty_level = models.CharField(max_length=20, choices=DifficultyLevel.choices)
    min_age = models.PositiveIntegerField(blank=True, null=True)
    max_weight = models.PositiveIntegerField(blank=True, null=True)
    min_weight = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False, help_text='Show this activity in the Trending Activities section on the homepage.')
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


class PackageUnavailableDate(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='unavailable_dates')
    date = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['package', 'date'], name='unique_package_unavailable_date'),
        ]

    def __str__(self):
        return f"{self.package.title} unavailable on {self.date}"

    def clean(self):
        if self.date and self.date < timezone.localdate():
            raise ValidationError({'date': 'Unavailable date cannot be in the past.'})


class ActivityUnavailableDate(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='unavailable_dates')
    date = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['activity', 'date'], name='unique_activity_unavailable_date'),
        ]

    def __str__(self):
        return f"{self.activity.name} unavailable on {self.date}"

    def clean(self):
        if self.date and self.date < timezone.localdate():
            raise ValidationError({'date': 'Unavailable date cannot be in the past.'})


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

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def savings_amount(self):
        original_price = self.original_price
        if original_price is None:
            return 0
        return original_price - self.sale_price


class BookingQuerySet(models.QuerySet):
    def visible_in_listings(self):
        return self.filter(Booking.visible_in_listings_q())


def _is_customer_account(user):
    return (
        user is not None
        and user.role == CustomUser.Role.CUSTOMER
        and not user.is_staff
        and not user.is_superuser
    )


class Booking(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash on arrival'
        ESEWA = 'ESEWA', 'eSewa'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    travel_date = models.DateField()
    number_of_people = models.PositiveIntegerField(default=1)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    transaction_reference = models.CharField(max_length=120, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    pickup_location = models.CharField(max_length=150, blank=True)
    nationality = models.CharField(max_length=80)
    emergency_contact = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def visible_in_listings_q(cls, prefix=''):
        return models.Q(**{f'{prefix}payment_status': cls.PaymentStatus.PAID}) | ~models.Q(**{f'{prefix}payment_method': cls.PaymentMethod.ESEWA})

    def __str__(self):
        return f"{self.package.title} - {self.full_name} - {self.travel_date}"

    def clean(self):
        if self.user_id:
            is_customer = (
                self.user.role == CustomUser.Role.CUSTOMER
                and not self.user.is_staff
                and not self.user.is_superuser
            )
            if not is_customer:
                raise ValidationError({'user': 'Only customers can book packages.'})

    def save(self, *args, **kwargs):
        if self.package_id and self.number_of_people:
            should_compute_total = self.total_amount is None or self.total_amount <= 0
            if should_compute_total and self.package.price is not None:
                self.total_amount = self.package.price * self.number_of_people

        if self.payment_status == self.PaymentStatus.PAID and self.paid_at is None:
            self.paid_at = timezone.now()
        elif self.payment_status in (self.PaymentStatus.PENDING, self.PaymentStatus.FAILED):
            self.paid_at = None

        self.full_clean()
        super().save(*args, **kwargs)


class ActivityBookingQuerySet(models.QuerySet):
    def visible_in_listings(self):
        return self.filter(ActivityBooking.visible_in_listings_q())


class ActivityBooking(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash on arrival'
        ESEWA = 'ESEWA', 'eSewa'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_bookings')
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    travel_date = models.DateField()
    number_of_people = models.PositiveIntegerField(default=1)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    transaction_reference = models.CharField(max_length=120, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    pickup_location = models.CharField(max_length=150, blank=True)
    nationality = models.CharField(max_length=80)
    emergency_contact = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ActivityBookingQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def visible_in_listings_q(cls, prefix=''):
        return models.Q(**{f'{prefix}payment_status': cls.PaymentStatus.PAID}) | ~models.Q(**{f'{prefix}payment_method': cls.PaymentMethod.ESEWA})

    def __str__(self):
        return f"{self.activity.name} - {self.full_name} - {self.travel_date}"

    def save(self, *args, **kwargs):
        if self.activity_id and self.number_of_people:
            should_compute_total = self.total_amount is None or self.total_amount <= 0
            if should_compute_total and self.activity.price is not None:
                self.total_amount = self.activity.price * self.number_of_people

        if self.payment_status == self.PaymentStatus.PAID and self.paid_at is None:
            self.paid_at = timezone.now()
        elif self.payment_status in (self.PaymentStatus.PENDING, self.PaymentStatus.FAILED):
            self.paid_at = None

        super().save(*args, **kwargs)


class PackageReview(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='package_reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['package', 'user'],
                name='unique_package_review_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.package.title} review by {self.user or 'Anonymous'}"

    def clean(self):
        if not self.user_id:
            raise ValidationError('A logged-in user is required to submit a review.')

        has_booking = Booking.objects.filter(
            user_id=self.user_id,
            package_id=self.package_id,
        ).visible_in_listings().exists()
        if not has_booking:
            raise ValidationError('Only users who booked this package can submit a review.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        _sync_package_average_rating(self.package_id)

    def delete(self, *args, **kwargs):
        package_id = self.package_id
        super().delete(*args, **kwargs)
        _sync_package_average_rating(package_id)


class ActivityReview(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['activity', 'user'],
                name='unique_activity_review_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.activity.name} review by {self.user or 'Anonymous'}"

    def clean(self):
        if not self.user_id:
            raise ValidationError('A logged-in user is required to submit a review.')

        has_booking = ActivityBooking.objects.filter(
            user_id=self.user_id,
            activity_id=self.activity_id,
        ).visible_in_listings().exists()
        if not has_booking:
            raise ValidationError('Only users who booked this activity can submit a review.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        _sync_activity_average_rating(self.activity_id)

    def delete(self, *args, **kwargs):
        activity_id = self.activity_id
        super().delete(*args, **kwargs)
        _sync_activity_average_rating(activity_id)


def _rounded_average_rating(queryset):
    avg_rating = queryset.aggregate(avg_rating=Avg('rating')).get('avg_rating')
    if avg_rating is None:
        return 0
    return round(float(avg_rating), 1)


def _sync_package_average_rating(package_id):
    if not package_id:
        return
    Package.objects.filter(pk=package_id).update(
        rating=_rounded_average_rating(PackageReview.objects.filter(package_id=package_id))
    )


def _sync_activity_average_rating(activity_id):
    if not activity_id:
        return
    Activity.objects.filter(pk=activity_id).update(
        rating=_rounded_average_rating(ActivityReview.objects.filter(activity_id=activity_id))
    )


class Inquiry(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='inquiries', null=True, blank=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='inquiries', null=True, blank=True)
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
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(package__isnull=False) & models.Q(activity__isnull=True))
                    | (models.Q(package__isnull=True) & models.Q(activity__isnull=False))
                ),
                name='inquiry_exactly_one_target',
            ),
        ]

    def clean(self):
        if self.user_id and not _is_customer_account(self.user):
            raise ValidationError({'user': 'Only customers can send inquiries.'})
        if bool(self.package_id) == bool(self.activity_id):
            raise ValidationError('Inquiry must reference either a package or an activity.')

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if self._state.adding and self.user_id and not _is_customer_account(self.user):
            raise ValidationError({'user': 'Only customers can send inquiries.'})

        if self.admin_reply and self.replied_at is None:
            self.replied_at = timezone.now()
        if not self.admin_reply:
            self.replied_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Inquiry: {self.target_name} ({self.customer_name})"

    @property
    def target_name(self):
        if self.package_id and self.package:
            return self.package.title
        if self.activity_id and self.activity:
            return self.activity.name
        return 'Unknown item'

    @property
    def target_type(self):
        if self.package_id:
            return 'Package'
        if self.activity_id:
            return 'Activity'
        return 'Item'

    @property
    def target_absolute_url(self):
        if self.package_id and self.package:
            return self.package.get_absolute_url()
        if self.activity_id:
            return reverse('activity_detail', kwargs={'pk': self.activity_id})
        return '#'

    @property
    def customer_name(self):
        if self.user_id and self.user:
            return self.user.get_full_name() or self.user.username
        return (self.full_name or '').strip() or 'Customer'

    @property
    def customer_email(self):
        if self.user_id and self.user:
            return (self.user.email or '').strip() or (self.email or '').strip()
        return (self.email or '').strip()

    @property
    def customer_phone(self):
        return (self.phone or '').strip()

    @property
    def has_vendor_reply(self):
        return self.messages.filter(sender_role__in=['VENDOR', 'STAFF']).exists() or bool((self.admin_reply or '').strip())


class InquiryMessage(models.Model):
    class SenderRole(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        VENDOR = 'VENDOR', 'Vendor'
        STAFF = 'STAFF', 'Staff'

    inquiry = models.ForeignKey(Inquiry, on_delete=models.CASCADE, related_name='messages')
    sender_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inquiry_messages',
    )
    sender_role = models.CharField(max_length=20, choices=SenderRole.choices, default=SenderRole.CUSTOMER)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f"{self.get_sender_role_display()} message on inquiry #{self.inquiry_id}"


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


def _sync_destination_cover_image(destination_id):
    if not destination_id:
        return

    images = DestinationImage.objects.filter(destination_id=destination_id).order_by('created_at', 'pk')
    primary = images.filter(is_primary=True).first() or images.first()
    cover_name = getattr(getattr(primary, 'image', None), 'name', None)
    Destination.objects.filter(pk=destination_id).update(hero_image=cover_name)


@receiver(post_save, sender=DestinationImage)
def _destination_image_post_save(sender, instance, **kwargs):
    _normalize_single_primary(DestinationImage, 'destination', instance.destination_id)
    _sync_destination_cover_image(instance.destination_id)


@receiver(post_delete, sender=DestinationImage)
def _destination_image_post_delete(sender, instance, **kwargs):
    file_name = getattr(instance.image, 'name', None)
    _normalize_single_primary(DestinationImage, 'destination', instance.destination_id)
    _sync_destination_cover_image(instance.destination_id)
    _delete_file_if_unreferenced(
        file_name,
        checks=[
            lambda: DestinationImage.objects.filter(image=file_name),
            lambda: Destination.objects.filter(hero_image=file_name),
        ],
    )


@receiver(pre_save, sender=Destination)
def _destination_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_hero_image_name = None
        return

    try:
        old_destination = sender.objects.only('hero_image').get(pk=instance.pk)
        instance._old_hero_image_name = old_destination.hero_image.name
    except sender.DoesNotExist:
        instance._old_hero_image_name = None


@receiver(post_save, sender=Destination)
def _destination_post_save(sender, instance, **kwargs):
    old_name = getattr(instance, '_old_hero_image_name', None)
    new_name = getattr(instance.hero_image, 'name', None)

    if old_name and old_name != new_name:
        _delete_file_if_unreferenced(
            old_name,
            checks=[
                lambda: Destination.objects.filter(hero_image=old_name),
                lambda: DestinationImage.objects.filter(image=old_name),
            ],
        )


@receiver(post_delete, sender=Destination)
def _destination_post_delete(sender, instance, **kwargs):
    file_name = getattr(instance.hero_image, 'name', None)
    _delete_file_if_unreferenced(
        file_name,
        checks=[
            lambda: Destination.objects.filter(hero_image=file_name),
            lambda: DestinationImage.objects.filter(image=file_name),
        ],
    )


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


@receiver(m2m_changed, sender=CustomUser.favorite_packages.through)
def _enforce_customer_favorite_access(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add':
        return

    if reverse:
        users = CustomUser.objects.filter(pk__in=pk_set)
        has_disallowed_user = any(not _is_customer_account(user) for user in users)
        if has_disallowed_user:
            raise ValidationError('Only customers can add packages to favorites.')
        return

    if not _is_customer_account(instance):
        raise ValidationError('Only customers can add packages to favorites.')


@receiver(m2m_changed, sender=CustomUser.favorite_activities.through)
def _enforce_customer_activity_favorite_access(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add':
        return

    if reverse:
        users = CustomUser.objects.filter(pk__in=pk_set)
        has_disallowed_user = any(not _is_customer_account(user) for user in users)
        if has_disallowed_user:
            raise ValidationError('Only customers can add activities to favorites.')
        return

    if not _is_customer_account(instance):
        raise ValidationError('Only customers can add activities to favorites.')
