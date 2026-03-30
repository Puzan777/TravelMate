from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0016_enforce_vendor_ownership_non_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='email',
            field=models.EmailField(default='unknown@example.com', max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='booking',
            name='emergency_contact',
            field=models.CharField(default='N/A', max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='booking',
            name='full_name',
            field=models.CharField(default='Unknown Traveler', max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='booking',
            name='nationality',
            field=models.CharField(default='Unknown', max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='booking',
            name='number_of_people',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='booking',
            name='phone',
            field=models.CharField(default='N/A', max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='booking',
            name='pickup_location',
            field=models.CharField(blank=True, default='', max_length=150),
            preserve_default=False,
        ),
    ]
