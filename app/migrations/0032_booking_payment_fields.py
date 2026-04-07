from decimal import Decimal

from django.db import migrations, models


def backfill_booking_totals(apps, schema_editor):
    Booking = apps.get_model('app', 'Booking')

    for booking in Booking.objects.select_related('package').all():
        package = booking.package
        if package is None:
            continue
        package_price = package.price or Decimal('0')
        people = booking.number_of_people or 0
        booking.total_amount = package_price * people
        booking.save(update_fields=['total_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0031_package_rejection_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='payment_method',
            field=models.CharField(
                choices=[('CASH', 'Cash on arrival'), ('ESEWA', 'eSewa'), ('BANK_TRANSFER', 'Bank transfer')],
                default='CASH',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='payment_status',
            field=models.CharField(
                choices=[('PENDING', 'Pending'), ('PAID', 'Paid'), ('FAILED', 'Failed'), ('REFUNDED', 'Refunded')],
                default='PENDING',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='transaction_reference',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='booking',
            name='total_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='booking',
            name='paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_booking_totals, migrations.RunPython.noop),
    ]
