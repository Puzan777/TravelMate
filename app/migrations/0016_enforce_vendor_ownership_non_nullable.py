# Generated manually to enforce vendor ownership after backfill

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0015_backfill_vendor_ownership'),
    ]

    operations = [
        migrations.AlterField(
            model_name='destination',
            name='vendor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='destinations',
                to='vendor.vendorprofile',
            ),
        ),
        migrations.AlterField(
            model_name='package',
            name='vendor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='packages',
                to='vendor.vendorprofile',
            ),
        ),
    ]
