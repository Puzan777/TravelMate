from django.db import migrations, models


def backfill_inquiry_thread_messages(apps, schema_editor):
    Inquiry = apps.get_model('app', 'Inquiry')
    InquiryMessage = apps.get_model('app', 'InquiryMessage')

    for inquiry in Inquiry.objects.all().iterator():
        customer_message = (inquiry.message or '').strip()
        if customer_message:
            customer_entry = InquiryMessage.objects.create(
                inquiry_id=inquiry.pk,
                sender_user_id=inquiry.user_id,
                sender_role='CUSTOMER',
                message=customer_message,
            )
            InquiryMessage.objects.filter(pk=customer_entry.pk).update(created_at=inquiry.created_at)

        vendor_reply = (inquiry.admin_reply or '').strip()
        if vendor_reply:
            replied_at = inquiry.replied_at or inquiry.created_at
            vendor_entry = InquiryMessage.objects.create(
                inquiry_id=inquiry.pk,
                sender_role='VENDOR',
                message=vendor_reply,
            )
            InquiryMessage.objects.filter(pk=vendor_entry.pk).update(created_at=replied_at)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0043_add_is_featured'),
    ]

    operations = [
        migrations.CreateModel(
            name='InquiryMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_role', models.CharField(choices=[('CUSTOMER', 'Customer'), ('VENDOR', 'Vendor'), ('STAFF', 'Staff')], default='CUSTOMER', max_length=20)),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('inquiry', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='messages', to='app.inquiry')),
                ('sender_user', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='inquiry_messages', to='app.customuser')),
            ],
            options={
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.RunPython(backfill_inquiry_thread_messages, noop_reverse),
    ]
