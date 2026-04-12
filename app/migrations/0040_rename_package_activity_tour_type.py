from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0039_activity_best_season_activity_city_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='package',
            old_name='activity',
            new_name='tour_type',
        ),
    ]
