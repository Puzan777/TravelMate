from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0027_packageimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotsale',
            name='activity',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name='hot_sale_entries', to='app.activity'),
        ),
        migrations.AlterField(
            model_name='hotsale',
            name='package',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name='hot_sale_entries', to='app.package'),
        ),
        migrations.AddConstraint(
            model_name='hotsale',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('activity__isnull', False), ('package__isnull', True)), models.Q(('activity__isnull', True), ('package__isnull', False)), _connector='OR'), name='hotsale_exactly_one_target'),
        ),
    ]
