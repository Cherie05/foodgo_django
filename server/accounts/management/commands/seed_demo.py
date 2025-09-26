# accounts/management/commands/seed_demo.py
from math import cos, radians
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from accounts.models import Category, Restaurant, Product

# -------------------------------------------------------------------
# Base location used to drop restaurants around the user
# -------------------------------------------------------------------
LAT0 = 17.99142
LON0 = 79.52525


def offset_m_to_latlon(lat0, lon0, dx_m=0.0, dy_m=0.0):
    """Meters east/west (dx), north/south (dy) -> degrees lat/lon."""
    dlat = dy_m / 111_111.0
    dlon = dx_m / (111_111.0 * cos(radians(lat0)))
    return (lat0 + dlat, lon0 + dlon)


# -------------------------------------------------------------------
# Canonical UI category names -> Ionicons used by your app
# (We will only create the ones actually used by products.)
# -------------------------------------------------------------------
CATEGORY_ICON_MAP = {
    "Burgers": "fast-food",
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
    "Seafood": "fish-outline",
    "BBQ": "flame-outline",
    "Breakfast": "cafe-outline",
    "Mexican": "restaurant",
    "Pasta": "pizza-outline",
    "Coffee": "cafe-outline",
    "Shake": "beer-outline",
}

# Aliases you might use in product “chip” -> canonical category
ALIAS_TO_CATEGORY = {
    "Burger": "Burgers",
    "Burgers": "Burgers",
    "Pizza": "Pizza",
    "Biryani": "Biryani",
    "Indian": "Indian",
    "Chinese": "Chinese",
    "Desserts": "Desserts",
    "Cafe": "Cafe",
    "Healthy": "Healthy",
    "Sandwiches": "Sandwiches",
    "Drinks": "Drinks",
    "Salad": "Salad",
    "Seafood": "Seafood",
    "BBQ": "BBQ",
    "Breakfast": "Breakfast",
    "Mexican": "Mexican",
    "Pasta": "Pasta",
    "Coffee": "Coffee",
    "Shake": "Shake",
}

# -------------------------------------------------------------------
# Catalog: Every restaurant has a non-empty product list
# Each product has: title, subtitle, price, chip (category alias)
# Images:
#   - Product image_url: deterministic picsum seed from restaurant+title
#   - Restaurant image_url: we set it to the FIRST product’s image
# -------------------------------------------------------------------
CATALOG = [
    {
        "name": "Cafe Morning Roast",
        "tags": "Cafe • Coffee • Sandwiches",
        "rating": 4.5,
        "eta_min": 12,
        "eta_max": 18,
        "delivery_free": True,
        "is_open": True,
        "offset": (300, -900),
        "products": [
            {"title": "Burger Ferguson", "subtitle": "Spicy Restaurant", "price": 40, "chip": "Burger"},
            {"title": "Cafecafachino", "subtitle": "Signature coffee", "price": 5, "chip": "Coffee"},
            {"title": "Rockin' Burgers", "subtitle": "House special", "price": 40, "chip": "Burger"},
            {"title": "Club Sandwich", "subtitle": "Classic", "price": 9, "chip": "Sandwiches"},
            {"title": "Avocado Toast", "subtitle": "Breakfast fav", "price": 7, "chip": "Breakfast"},
            {"title": "Chocolate Shake", "subtitle": "Thick & cold", "price": 6, "chip": "Shake"},
        ],
    },
    {
        "name": "Spice Route Biryani House",
        "tags": "Biryani • North Indian • Family Meals",
        "rating": 4.6,
        "eta_min": 18,
        "eta_max": 28,
        "delivery_free": True,
        "is_open": True,
        "offset": (350, 220),
        "products": [
            {"title": "Hyderabadi Biryani", "subtitle": "Aromatic spices", "price": 11, "chip": "Biryani"},
            {"title": "Chicken Biryani", "subtitle": "Family pack", "price": 16, "chip": "Biryani"},
            {"title": "Paneer Butter Masala", "subtitle": "Rich & creamy", "price": 12, "chip": "Indian"},
            {"title": "Butter Naan", "subtitle": "Fresh tandoor", "price": 3, "chip": "Indian"},
            {"title": "Veg Thali", "subtitle": "Assorted platter", "price": 14, "chip": "Indian"},
            {"title": "Gulab Jamun", "subtitle": "Dessert", "price": 4, "chip": "Desserts"},
        ],
    },
    {
        "name": "Dragon Wok Express",
        "tags": "Chinese • Noodles • Dumplings",
        "rating": 4.4,
        "eta_min": 16,
        "eta_max": 24,
        "delivery_free": True,
        "is_open": True,
        "offset": (-600, 150),
        "products": [
            {"title": "Veg Hakka Noodles", "subtitle": "Stir-fried", "price": 9, "chip": "Chinese"},
            {"title": "Chicken Manchurian", "subtitle": "House gravy", "price": 11, "chip": "Chinese"},
            {"title": "Dimsum Platter", "subtitle": "Assorted", "price": 12, "chip": "Chinese"},
            {"title": "Kung Pao Chicken", "subtitle": "Spicy peanuts", "price": 12, "chip": "Chinese"},
            {"title": "Spring Rolls", "subtitle": "Crispy starter", "price": 6, "chip": "Chinese"},
            {"title": "Jasmine Tea", "subtitle": "Hot", "price": 3, "chip": "Drinks"},
        ],
    },
    {
        "name": "La Pizzeria Napoli",
        "tags": "Pizza • Italian • Family Packs",
        "rating": 4.7,
        "eta_min": 20,
        "eta_max": 30,
        "delivery_free": True,
        "is_open": True,
        "offset": (900, -300),
        "products": [
            {"title": "Margherita", "subtitle": "Fresh basil", "price": 10, "chip": "Pizza"},
            {"title": "Pepperoni", "subtitle": "Classic", "price": 12, "chip": "Pizza"},
            {"title": "BBQ Chicken Pizza", "subtitle": "Smoky", "price": 13, "chip": "Pizza"},
            {"title": "Truffle Pasta", "subtitle": "Rich & earthy", "price": 14, "chip": "Pasta"},
            {"title": "Garlic Bread", "subtitle": "With cheese", "price": 5, "chip": "Pizza"},
            {"title": "Tiramisu", "subtitle": "Dessert", "price": 6, "chip": "Desserts"},
        ],
    },
    {
        "name": "Green Bowl Kitchen",
        "tags": "Healthy • Salad • Bowls",
        "rating": 4.3,
        "eta_min": 10,
        "eta_max": 20,
        "delivery_free": True,
        "is_open": True,
        "offset": (-200, -600),
        "products": [
            {"title": "Quinoa Power Bowl", "subtitle": "Protein pack", "price": 11, "chip": "Healthy"},
            {"title": "Caesar Salad", "subtitle": "Crisp", "price": 9, "chip": "Salad"},
            {"title": "Avocado Salad", "subtitle": "Fresh & zesty", "price": 10, "chip": "Salad"},
            {"title": "Grilled Veg Platter", "subtitle": "Light & tasty", "price": 12, "chip": "Healthy"},
            {"title": "Green Smoothie", "subtitle": "Spinach & apple", "price": 6, "chip": "Drinks"},
            {"title": "Fruit Bowl", "subtitle": "Seasonal", "price": 7, "chip": "Healthy"},
        ],
    },
    {
        "name": "BBQ Pit Stop",
        "tags": "Grill • BBQ • Smoked Meats",
        "rating": 4.5,
        "eta_min": 22,
        "eta_max": 32,
        "delivery_free": False,
        "is_open": True,
        "offset": (1200, 450),
        "products": [
            {"title": "Smoked Brisket", "subtitle": "12h smoked", "price": 18, "chip": "BBQ"},
            {"title": "BBQ Ribs", "subtitle": "Sticky glaze", "price": 16, "chip": "BBQ"},
            {"title": "BBQ Smash Burger", "subtitle": "Double patty", "price": 13, "chip": "Burgers"},
            {"title": "Corn on the Cob", "subtitle": "Butter", "price": 4, "chip": "BBQ"},
            {"title": "Coleslaw", "subtitle": "Creamy", "price": 3, "chip": "BBQ"},
            {"title": "Iced Tea", "subtitle": "House brew", "price": 3, "chip": "Drinks"},
        ],
    },
    {
        "name": "Marina Seafood Shack",
        "tags": "Seafood • Grills • Platters",
        "rating": 4.2,
        "eta_min": 18,
        "eta_max": 26,
        "delivery_free": True,
        "is_open": True,
        "offset": (-1000, 300),
        "products": [
            {"title": "Grilled Prawns", "subtitle": "Lemon butter", "price": 16, "chip": "Seafood"},
            {"title": "Fish & Chips", "subtitle": "Crispy batter", "price": 12, "chip": "Seafood"},
            {"title": "Seafood Platter", "subtitle": "For two", "price": 24, "chip": "Seafood"},
            {"title": "Lobster Roll", "subtitle": "Buttery brioche", "price": 19, "chip": "Seafood"},
            {"title": "Calamari Rings", "subtitle": "With aioli", "price": 10, "chip": "Seafood"},
            {"title": "Lime Soda", "subtitle": "Fresh", "price": 3, "chip": "Drinks"},
        ],
    },
    {
        "name": "Fiesta Mexicana",
        "tags": "Mexican • Tacos • Burritos",
        "rating": 4.4,
        "eta_min": 16,
        "eta_max": 24,
        "delivery_free": True,
        "is_open": True,
        "offset": (600, 800),
        "products": [
            {"title": "Tacos Al Pastor", "subtitle": "Pineapple", "price": 11, "chip": "Mexican"},
            {"title": "Chicken Burrito", "subtitle": "Cheesy", "price": 12, "chip": "Mexican"},
            {"title": "Quesadillas", "subtitle": "Oozy cheese", "price": 10, "chip": "Mexican"},
            {"title": "Loaded Nachos", "subtitle": "Shareable", "price": 9, "chip": "Mexican"},
            {"title": "Churros", "subtitle": "Cinnamon sugar", "price": 5, "chip": "Desserts"},
            {"title": "Horchata", "subtitle": "Sweet rice milk", "price": 4, "chip": "Drinks"},
        ],
    },
    {
        "name": "Sweet Treats Corner",
        "tags": "Desserts • Shakes • Ice Cream",
        "rating": 4.6,
        "eta_min": 10,
        "eta_max": 16,
        "delivery_free": True,
        "is_open": True,
        "offset": (-850, -750),
        "products": [
            {"title": "Chocolate Lava Cake", "subtitle": "Warm center", "price": 6, "chip": "Desserts"},
            {"title": "Strawberry Sundae", "subtitle": "Whipped cream", "price": 5, "chip": "Desserts"},
            {"title": "Banana Split", "subtitle": "Classic", "price": 6, "chip": "Desserts"},
            {"title": "Cheesecake Slice", "subtitle": "New York style", "price": 6, "chip": "Desserts"},
            {"title": "Thick Shake", "subtitle": "Chocolate/Vanilla", "price": 5, "chip": "Shake"},
            {"title": "Iced Mocha", "subtitle": "Sweet coffee", "price": 4, "chip": "Drinks"},
        ],
    },
    {
        "name": "Early Bird Breakfast Co.",
        "tags": "Breakfast • Coffee • Sandwiches",
        "rating": 4.3,
        "eta_min": 10,
        "eta_max": 18,
        "delivery_free": True,
        "is_open": True,
        "offset": (150, 1050),
        "products": [
            {"title": "Pancake Stack", "subtitle": "Maple syrup", "price": 8, "chip": "Breakfast"},
            {"title": "French Toast", "subtitle": "Cinnamon", "price": 8, "chip": "Breakfast"},
            {"title": "Egg & Cheese Sandwich", "subtitle": "Brioche", "price": 7, "chip": "Sandwiches"},
            {"title": "Omelette Meal", "subtitle": "3 eggs", "price": 9, "chip": "Breakfast"},
            {"title": "Hash Browns", "subtitle": "Crispy", "price": 4, "chip": "Breakfast"},
            {"title": "Cappuccino", "subtitle": "Foamy", "price": 4, "chip": "Coffee"},
        ],
    },
]


def _canon_category(chip: str) -> str:
    """Map a product chip/alias to canonical category name."""
    return ALIAS_TO_CATEGORY.get(chip, chip)


def _picsum(seed: str, w: int, h: int) -> str:
    seed = seed.strip().replace(" ", "-").lower()
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


class Command(BaseCommand):
    help = "Seed demo data: restaurants, products, categories. Ensures images exist and every category has products."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing Restaurants & Products first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            Product.objects.all().delete()
            Restaurant.objects.all().delete()

        # 1) Build the set of categories actually used by products
        used_categories = set()
        for r in CATALOG:
            for p in r["products"]:
                used_categories.add(_canon_category(p["chip"]))

        # keep only categories that have icons available
        used_categories = [c for c in used_categories if c in CATEGORY_ICON_MAP]

        # 2) Upsert those categories
        name_to_cat = {}
        for name in sorted(used_categories):
            icon = CATEGORY_ICON_MAP[name]
            cat, created = Category.objects.get_or_create(name=name, defaults={"icon": icon})
            if not created and cat.icon != icon:
                cat.icon = icon
                cat.save(update_fields=["icon"])
            name_to_cat[name] = cat
        self.stdout.write(self.style.SUCCESS(f"Upserted {len(name_to_cat)} categories (only ones used by products)."))

        # 3) Upsert restaurants + products (and set restaurant image from 1st product)
        rest_created = 0
        prod_count_total = 0

        for r in CATALOG:
            dx, dy = r["offset"]
            lat, lon = offset_m_to_latlon(LAT0, LON0, dx_m=dx, dy_m=dy)

            # provisional image = first product's image (we build it below)
            first_prod = r["products"][0]
            first_img = _picsum(f"{r['name']}--{first_prod['title']}", 900, 450)

            rest_obj, was_created = Restaurant.objects.get_or_create(
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
                    "image_url": first_img,
                    "created_at": timezone.now(),
                },
            )
            if not was_created:
                rest_obj.tags = r["tags"]
                rest_obj.rating = r["rating"]
                rest_obj.eta_min = r["eta_min"]
                rest_obj.eta_max = r["eta_max"]
                rest_obj.delivery_free = r["delivery_free"]
                rest_obj.is_open = r["is_open"]
                rest_obj.latitude = lat
                rest_obj.longitude = lon
                # always ensure image_url present
                if not rest_obj.image_url:
                    rest_obj.image_url = first_img
                rest_obj.save()

            # create/update products and collect categories for this restaurant
            cat_for_rest = set()
            created_here = 0
            for p in r["products"]:
                canon = _canon_category(p["chip"])
                if canon not in name_to_cat:
                    # skip products whose category we didn't whitelist (shouldn't happen)
                    continue

                img_url = _picsum(f"{r['name']}--{p['title']}", 700, 420)

                prod_obj, prod_created = Product.objects.get_or_create(
                    restaurant=rest_obj,
                    title=p["title"],
                    defaults={
                        "subtitle": p.get("subtitle", ""),
                        "price": p.get("price", 0),
                        "is_available": True,
                        "image_url": img_url,
                    },
                )
                if not prod_created:
                    prod_obj.subtitle = p.get("subtitle", prod_obj.subtitle)
                    prod_obj.price = p.get("price", prod_obj.price)
                    prod_obj.is_available = True
                    # keep a stable image url (always set)
                    prod_obj.image_url = img_url
                    prod_obj.save()

                # set product -> category
                prod_obj.categories.set([name_to_cat[canon]])
                cat_for_rest.add(name_to_cat[canon].id)

                created_here += 1 if prod_created else 0
                prod_count_total += 1

            # update restaurant categories to those used by its products
            rest_obj.categories.set(list(cat_for_rest))

            # ensure restaurant has an image_url (use first product)
            try:
                first_product_obj = rest_obj.products.order_by("id").first()
                if first_product_obj and first_product_obj.image_url and rest_obj.image_url != first_product_obj.image_url:
                    # If current image is blank or different, set to first product's image
                    if not rest_obj.image_url:
                        rest_obj.image_url = first_product_obj.image_url
                        rest_obj.save(update_fields=["image_url"])
            except Exception:
                pass

            rest_created += 1 if was_created else 0
            self.stdout.write(
                self.style.SUCCESS(
                    f"Upserted restaurant '{rest_obj.name}' "
                    f"({created_here} new products, total now {rest_obj.products.count()})"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Restaurants created: {rest_created}. Products processed: {prod_count_total}."))
        self.stdout.write(self.style.SUCCESS("All restaurants have products, all categories are in use, all images set."))
