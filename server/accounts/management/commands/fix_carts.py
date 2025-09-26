from django.core.management.base import BaseCommand
from django.db import transaction
from collections import defaultdict

from accounts.models import Cart, CartItem

class Command(BaseCommand):
    help = "Merge duplicate active carts per user so only one remains."

    def handle(self, *args, **options):
        by_user = defaultdict(list)
        for c in Cart.objects.filter(is_active=True).order_by("user_id", "-updated_at", "-id"):
            by_user[c.user_id].append(c)

        merged_users = 0
        with transaction.atomic():
            for user_id, carts in by_user.items():
                if len(carts) <= 1:
                    continue
                primary = carts[0]
                for dup in carts[1:]:
                    for it in dup.items.select_related("product"):
                        merged, created = CartItem.objects.get_or_create(
                            cart=primary,
                            product=it.product,
                            defaults={"qty": it.qty, "title": it.title, "unit_price": it.unit_price},
                        )
                        if not created:
                            merged.qty += it.qty
                            merged.save(update_fields=["qty"])
                    dup.is_active = False
                    dup.save(update_fields=["is_active"])
                merged_users += 1

        self.stdout.write(self.style.SUCCESS(f"Merged duplicate carts for {merged_users} user(s)."))
