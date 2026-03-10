from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_inquiry'),
    ]

    operations = [
        migrations.AddField(
            model_name='inquiry',
            name='admin_reply',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='inquiry',
            name='replied_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
