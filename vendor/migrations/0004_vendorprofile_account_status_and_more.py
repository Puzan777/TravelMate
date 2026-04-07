from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vendor', '0003_vendorprofile_account_holder_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='account_status',
            field=models.CharField(
                choices=[('ACTIVE', 'Active'), ('DEACTIVATED', 'Deactivated')],
                default='ACTIVE',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='status_changed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='status_reason',
            field=models.TextField(blank=True),
        ),
    ]
