# accounts/management/commands/seed_demo.py
from math import cos, radians
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Category, Restaurant, Product


LAT0 = 17.99142
LON0 = 79.52525


def offset_m_to_latlon(lat0, lon0, dx_m=0.0, dy_m=0.0):
    """Meters east/west (dx), north/south (dy) -> degrees lat/lon."""
    dlat = dy_m / 111_111.0
    dlon = dx_m / (111_111.0 * cos(radians(lat0)))
    return (lat0 + dlat, lon0 + dlon)


def upsert_category(name, icon):
    cat, _ = Category.objects.get_or_create(name=name, defaults={"icon": icon})
    if cat.icon != icon:
        cat.icon = icon
        cat.save(update_fields=["icon"])
    return cat


RESTAURANTS = [
    {
        "name": "Cafe Morning Roast",
        "tags": "Cafe • Coffee • Sandwiches",
        "rating": 4.5, "eta_min": 12, "eta_max": 18, "delivery_free": True, "is_open": True,
        "offset": (300, -900),
        "cats": ["Cafe"],
        # optional demo image
        "image_url": "https://picsum.photos/seed/cafe/800/400",
    },
    {
        "name": "Spice Route Biryani House",
        "tags": "Biryani • North Indian • Family Meals",
        "rating": 4.6, "eta_min": 18, "eta_max": 28, "delivery_free": True, "is_open": True,
        "offset": (350, 220),
        "cats": ["Biryani", "Indian"],
        "image_url": "https://picsum.photos/seed/biryani/800/400",
    },
]

PRODUCTS = [
    # attach to Cafe Morning Roast
    ("Cafe Morning Roast", [
        { "title": "Burger Ferguson", "subtitle": "Spicy Restaurant", "price": 40, "chip": "Burger" },
        { "title": "Rockin' Burgers", "subtitle": "Cafecafachino",  "price": 40, "chip": "Burger" },
        { "title": "Cheese Delight",  "subtitle": "Spicy Restaurant", "price": 42, "chip": "Burger" },
        { "title": "BBQ Smash",       "subtitle": "Cafecafachino",  "price": 45, "chip": "Burger" },
        { "title": "Double Patty",    "subtitle": "Spicy Restaurant", "price": 48, "chip": "Burger" },
        { "title": "Veggie Crunch",   "subtitle": "Cafecafachino",  "price": 38, "chip": "Burger" },
    ]),
]

CATEGORY_ICONS = {
    "Burgers": "fast-food",
    "Burger": "fast-food",      # alias used by chip text
    "Pizza": "pizza",
    "Biryani": "flame",
    "Indian": "restaurant",
    "Chinese": "leaf",
    "Desserts": "ice-cream-outline",
    "Cafe": "cafe-outline",
    "Healthy": "nutrition-outline",
    "Sandwiches": "fast-food",
    "Drinks": "beer-outline",
    "Salad": "nutrition-outline",
}


class Command(BaseCommand):
    help = "Seed demo categories, restaurants and products near the given coords."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing Restaurants & Products first.")

    def handle(self, *args, **opts):
        if opts["reset"]:
            Product.objects.all().delete()
            Restaurant.objects.all().delete()

        # 1) Categories (idempotent)
        cats = {}
        for name, icon in CATEGORY_ICONS.items():
            cats[name] = upsert_category(name, icon)
        self.stdout.write(self.style.SUCCESS(f"Upserted {len(cats)} categories"))

        # 2) Restaurants (idempotent)
        created_rest = 0
        name_to_rest = {}
        for r in RESTAURANTS:
            dx, dy = r["offset"]
            lat, lon = offset_m_to_latlon(LAT0, LON0, dx_m=dx, dy_m=dy)

            obj, was_created = Restaurant.objects.get_or_create(
                name=r["name"],
                defaults={
                    "tags": r["tags"],
                    "rating": r["rating"],
                    "eta_min": r["eta_min"],
                    "eta_max": r["eta_max"],
                    "delivery_free": r["delivery_free"],
                    "is_open": r["is_open"],
                    "latitude": lat,
                    "longitude": lon,
                    "image_url": r.get("image_url", ""),
                    "created_at": timezone.now(),
                },
            )
            if not was_created:
                # keep data fresh
                obj.tags = r["tags"]
                obj.rating = r["rating"]
                obj.eta_min = r["eta_min"]
                obj.eta_max = r["eta_max"]
                obj.delivery_free = r["delivery_free"]
                obj.is_open = r["is_open"]
                obj.latitude = lat
                obj.longitude = lon
                if r.get("image_url"):
                    obj.image_url = r["image_url"]
                obj.save()

            # set M2M categories
            chosen = [cats.get(c) for c in r["cats"] if c in cats]
            obj.categories.set(chosen)

            created_rest += 1 if was_created else 0
            name_to_rest[obj.name] = obj

        self.stdout.write(self.style.SUCCESS(f"Upserted {len(RESTAURANTS)} restaurants ({created_rest} created)"))

        # 3) Products (idempotent)
        total_seeded = 0
        for rest_name, prods in PRODUCTS:
            rest = name_to_rest.get(rest_name) or Restaurant.objects.filter(name__iexact=rest_name).first()
            if not rest:
                self.stdout.write(self.style.WARNING(f"Restaurant '{rest_name}' not found; skipping products."))
                continue

            for p in prods:
                obj, created = Product.objects.get_or_create(
                    restaurant=rest,
                    title=p["title"],
                    defaults={
                        "subtitle": p.get("subtitle", ""),
                        "price": p.get("price", 0),
                        "is_available": True,
                        # demo image:
                        "image_url": "https://picsum.photos/seed/" + p["title"].replace(" ", "-").lower() + "/600/400",
                    },
                )
                chip = p.get("chip")
                m2m = []
                # map chip names to the real category names you configured
                if chip == "Burger":
                    m2m.append(cats["Burgers"])
                elif chip and chip in cats:
                    m2m.append(cats[chip])
                obj.categories.set(m2m)
                if not created:
                    obj.subtitle = p.get("subtitle", obj.subtitle)
                    obj.price = p.get("price", obj.price)
                    obj.is_available = True
                    obj.save()
                total_seeded += 1

            self.stdout.write(self.style.SUCCESS(f"Seeded {len(prods)} products for {rest.name}"))

        self.stdout.write(self.style.SUCCESS("Done."))
