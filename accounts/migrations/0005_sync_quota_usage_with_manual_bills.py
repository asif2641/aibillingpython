from django.db import migrations


def sync_quota_usage(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Bill = apps.get_model("bills", "Bill")

    for user in User.objects.filter(is_superuser=False):
        active_bills_count = Bill.objects.filter(created_by=user, is_deleted=False).count()
        if active_bills_count > user.scans_used_this_month:
            user.scans_used_this_month = active_bills_count
            user.save(update_fields=["scans_used_this_month"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_subscriptionpaymentrequest"),
        ("bills", "0004_bill_discrepancy_resolved_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_quota_usage, noop),
    ]
