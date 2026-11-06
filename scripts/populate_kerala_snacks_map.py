"""
Populates the complete 'Snacks Map of Kerala' catalogue in OnFresh.
Adds all 17 traditional Kerala snacks with their Malayalam names, descriptions,
retail and wholesale variants, and initial stock items.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.products.models import Category, Product, ProductVariant
from apps.inventory.models import StockItem

SNACKS_MAP_DATA = [
    {
        "name": "Nendrakai Chips (Classic Salted Banana Chips)",
        "slug": "kerala-nendran-banana-chips",
        "category_slug": "banana-chips",
        "short_description": "Thinly sliced raw Nendran bananas fried crisp in 100% pure coconut oil with sea salt.",
        "description": "The quintessential snack of God's Own Country. Made from prime raw Nendran plantains sourced directly from Idukki high-range farms, batch-fried each sunrise in cold-pressed coconut oil, seasoned gently with turmeric and rock salt.",
        "ingredients": "Raw Nendran Bananas, Pure Cold-Pressed Coconut Oil, Turmeric Powder, Rock Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("110.00"), "ws_price": Decimal("85.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("210.00"), "ws_price": Decimal("165.00"), "moq": 10},
            {"weight": Decimal("1.00"), "unit": "kg", "price": Decimal("400.00"), "ws_price": Decimal("310.00"), "moq": 5},
        ]
    },
    {
        "name": "Masala Nendrakai Chips (Spicy Banana Chips)",
        "slug": "masala-nendrakai-chips",
        "category_slug": "banana-chips",
        "short_description": "Crisp Nendran banana chips coated in our signature roasted red chilli, black salt, and spice blend.",
        "description": "A zesty twist on Kerala's crown snack. Ultra-crispy Nendran banana slices tossed with Kashmiri chilli, crushed black pepper, amchur, and roasted spices for an addictive tea-time kick.",
        "ingredients": "Raw Nendran Bananas, Pure Coconut Oil, Red Chilli Powder, Black Salt, Chaat Spices, Rock Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("115.00"), "ws_price": Decimal("90.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("220.00"), "ws_price": Decimal("170.00"), "moq": 10},
            {"weight": Decimal("1.00"), "unit": "kg", "price": Decimal("420.00"), "ws_price": Decimal("320.00"), "moq": 5},
        ]
    },
    {
        "name": "Paya Chips (Ripe Sweet Banana Chips)",
        "slug": "paya-chips",
        "category_slug": "banana-chips",
        "short_description": "Sliced ripe Nendran bananas fried slowly until caramelized, crunchy, and naturally sweet.",
        "description": "Known as Pazham Varuthathu or Paya Chips. Made from naturally ripened sweet Nendran bananas, gently fried to deep golden perfection. 100% natural sweetness with zero added artificial sugar.",
        "ingredients": "Naturally Ripened Nendran Bananas, Pure Coconut Oil",
        "shelf_life": "45 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("125.00"), "ws_price": Decimal("98.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("240.00"), "ws_price": Decimal("185.00"), "moq": 10},
        ]
    },
    {
        "name": "Sarkaravarati Upperi (Jaggery Coated Banana Chips)",
        "slug": "sharkkara-varatti",
        "category_slug": "banana-chips",
        "short_description": "Thick-cut banana chunks coated with organic Marayoor jaggery, dry ginger, and cardamom.",
        "description": "A festival imperative on every Kerala Onam Sadya leaf. Thick Nendran plantain cubes fried crisp and tossed in concentrated organic jaggery syrup, ground ginger (chukku), roasted cumin, and fragrant green cardamom powder.",
        "ingredients": "Raw Nendran Bananas, Marayoor Jaggery, Coconut Oil, Dry Ginger Powder, Cumin, Cardamom",
        "shelf_life": "90 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("130.00"), "ws_price": Decimal("100.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("250.00"), "ws_price": Decimal("195.00"), "moq": 10},
            {"weight": Decimal("1.00"), "unit": "kg", "price": Decimal("480.00"), "ws_price": Decimal("375.00"), "moq": 5},
        ]
    },
    {
        "name": "Chakka Chips (Raw Jackfruit Chips)",
        "slug": "jackfruit-chips",
        "category_slug": "traditional-snacks",
        "short_description": "Sun-ripened farm-fresh raw jackfruit bulbs fried in pure coconut oil with a distinctive high-range crunch.",
        "description": "Harvested fresh from the Idukki hills. Mature raw jackfruit pods are sliced and fried until blistered, crisp, and golden. Irresistible natural flavour and loud satisfying crunch.",
        "ingredients": "Raw Jackfruit (Varikka Chakka), Pure Coconut Oil, Rock Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("135.00"), "ws_price": Decimal("105.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("320.00"), "ws_price": Decimal("250.00"), "moq": 10},
        ]
    },
    {
        "name": "Poola Chips (Classic Tapioca Chips)",
        "slug": "poola-chips",
        "category_slug": "traditional-snacks",
        "short_description": "Crisp round sliced cassava (kappa) chips seasoned with sea salt and light red chilli.",
        "description": "Also cherished as Kappa Chips across Kerala. Freshly harvested cassava roots thinly round-sliced and fried in coconut oil. Light, exceptionally crispy, and lightly salted.",
        "ingredients": "Fresh Cassava / Tapioca, Coconut Oil, Red Chilli Powder, Rock Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("85.00"), "ws_price": Decimal("65.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("160.00"), "ws_price": Decimal("125.00"), "moq": 10},
        ]
    },
    {
        "name": "Stick Poola (Tapioca Finger Chips)",
        "slug": "stick-poola",
        "category_slug": "traditional-snacks",
        "short_description": "Matchstick-cut crunchy tapioca batons seasoned with chilli, garlic, and fresh curry leaves.",
        "description": "The street-side favourite of Kerala tea shops. Thinly julienned tapioca fingers fried to an amber crunch, tossed with coarse pepper and fragrant fried curry leaves.",
        "ingredients": "Tapioca (Kappa), Coconut Oil, Red Chilli Flakes, Garlic, Curry Leaves, Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("90.00"), "ws_price": Decimal("70.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("170.00"), "ws_price": Decimal("135.00"), "moq": 10},
        ]
    },
    {
        "name": "Thenkuzhal Murukku",
        "slug": "thenkuzhal-murukku",
        "category_slug": "traditional-snacks",
        "short_description": "Tubular crunchy rice and urad dal savoury snack scented with cumin and sesame.",
        "description": "Traditional hollow, cylindrical Murukku with a distinct smooth texture. Prepared with freshly ground raw rice flour, roasted urad dal flour, and fragrant cumin seeds for a brittle, satisfying snap.",
        "ingredients": "Rice Flour, Urad Dal, Pure Butter, Sesame Seeds, Cumin, Coconut Oil, Salt",
        "shelf_life": "75 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("95.00"), "ws_price": Decimal("72.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("180.00"), "ws_price": Decimal("140.00"), "moq": 10},
        ]
    },
    {
        "name": "Kai Murukku (Handmade Twisted Murukku)",
        "slug": "kai-murukku",
        "category_slug": "traditional-snacks",
        "short_description": "Artisanal hand-twisted spirals of rice flour and pure butter with asafoetida aroma.",
        "description": "A masterwork of traditional Kerala snack-making craft. Twisted by hand without moulds or presses, creating intricate ridged spirals that fry up exceptionally light, melt-in-the-mouth, and buttery.",
        "ingredients": "Raw Rice Flour, Butter, Urad Dal, Asafoetida (Hing), Cumin, Salt, Coconut Oil",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("110.00"), "ws_price": Decimal("85.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("210.00"), "ws_price": Decimal("165.00"), "moq": 10},
        ]
    },
    {
        "name": "Ring Murukku (Chegodilu Rings)",
        "slug": "ring-murukku",
        "category_slug": "traditional-snacks",
        "short_description": "Crisp golden hollow rings infused with butter, ajwain, and roasted sesame.",
        "description": "Fun, bite-sized crunchy rings shaped with seasoned rice and moong dal dough. Lightly golden and fragrant with toasted sesame and ajwain seeds.",
        "ingredients": "Rice Flour, Moong Dal, Butter, Ajwain, White Sesame, Coconut Oil, Salt",
        "shelf_life": "60 Days",
        "is_featured": False,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("90.00"), "ws_price": Decimal("68.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("170.00"), "ws_price": Decimal("130.00"), "moq": 10},
        ]
    },
    {
        "name": "Ribbon Pakavada (Pakkavada)",
        "slug": "ribbon-pakavada",
        "category_slug": "traditional-snacks",
        "short_description": "Ribbon-thin savoury strips of gram flour and rice flour fried with fresh green curry leaves.",
        "description": "The quintessential snack sold at every Kerala railway station and tea stall. Thin flat strips with wavy edges, fried with red chillies and whole aromatic curry leaves.",
        "ingredients": "Besan (Gram Flour), Rice Flour, Red Chilli, Asafoetida, Curry Leaves, Coconut Oil, Salt",
        "shelf_life": "60 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("95.00"), "ws_price": Decimal("72.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("180.00"), "ws_price": Decimal("140.00"), "moq": 10},
        ]
    },
    {
        "name": "Special Kerala Mixture",
        "slug": "special-spicy-kerala-mixture",
        "category_slug": "mixture-savouries",
        "short_description": "Spicy blend of crispy sev, boondi, fried peanuts, roasted curry leaves, and garlic.",
        "description": "A complex savoury symphony. Freshly extruded spiced chickpea sev, crunchy kara boondi, roasted groundnuts, split dal, and crisp curry leaves tossed in crushed chilli powder.",
        "ingredients": "Gram Flour, Peanuts, Fried Gram Dal, Curry Leaves, Garlic, Red Chilli Powder, Asafoetida, Coconut Oil, Salt",
        "shelf_life": "75 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("95.00"), "ws_price": Decimal("72.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("180.00"), "ws_price": Decimal("140.00"), "moq": 10},
            {"weight": Decimal("1.00"), "unit": "kg", "price": Decimal("350.00"), "ws_price": Decimal("270.00"), "moq": 5},
        ]
    },
    {
        "name": "Masala Kadala (Spicy Fried Peanuts)",
        "slug": "masala-kadala",
        "category_slug": "mixture-savouries",
        "short_description": "Crunchy roasted peanuts enrobed in a fiery garlic, chilli, and curry leaf crust.",
        "description": "Selected premium plump groundnuts double-fried to an aromatic dark crunch with a savoury chickpea flour, red chilli, and crushed garlic coat.",
        "ingredients": "Peanuts (Kadala), Gram Flour, Rice Flour, Red Chilli Powder, Garlic, Curry Leaves, Salt, Oil",
        "shelf_life": "75 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("250.00"), "unit": "g", "price": Decimal("90.00"), "ws_price": Decimal("68.00"), "moq": 10},
            {"weight": Decimal("500.00"), "unit": "g", "price": Decimal("170.00"), "ws_price": Decimal("130.00"), "moq": 10},
        ]
    },
    {
        "name": "Masala Chola (Spiced Corn Flakes Mixture)",
        "slug": "masala-chola",
        "category_slug": "mixture-savouries",
        "short_description": "Crisp roasted corn flakes tossed with fried peanuts, curry leaves, and savoury chaat spices.",
        "description": "Golden sweet corn flakes flashed in hot oil to an airy crisp, combined with roasted groundnuts, cashews, and a sweet-tangy spice dust.",
        "ingredients": "Corn Flakes, Peanuts, Curry Leaves, Turmeric, Red Chilli, Chaat Masala, Salt, Oil",
        "shelf_life": "75 Days",
        "is_featured": True,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("85.00"), "ws_price": Decimal("64.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("160.00"), "ws_price": Decimal("122.00"), "moq": 10},
        ]
    },
    {
        "name": "Uppu Seedai (Salted Crunch Balls)",
        "slug": "uppu-seedai",
        "category_slug": "traditional-snacks",
        "short_description": "Miniature round crunchy marble balls made with roasted rice flour, butter, and sesame.",
        "description": "Heritage Kerala teatime snack. Tiny hand-rolled dough balls fried to an even tan crispiness. Incredible crunch with an unmistakable butter and sesame finish.",
        "ingredients": "Raw Rice Flour, Urad Dal, Butter, White Sesame, Asafoetida, Coconut Oil, Salt",
        "shelf_life": "60 Days",
        "is_featured": False,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("95.00"), "ws_price": Decimal("72.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("180.00"), "ws_price": Decimal("140.00"), "moq": 10},
        ]
    },
    {
        "name": "Vella Seedai (Jaggery Sweet Seedai)",
        "slug": "vella-seedai",
        "category_slug": "traditional-snacks",
        "short_description": "Sweet crunchy seedai balls caramelized with Marayoor jaggery, grated coconut, and cardamom.",
        "description": "The sweet twin of Uppu Seedai. Dough enriched with thick melted jaggery syrup, toasted coconut bits, and freshly ground cardamom.",
        "ingredients": "Rice Flour, Urad Dal, Organic Jaggery, Fresh Coconut Bits, Cardamom, Ghee, Oil",
        "shelf_life": "45 Days",
        "is_featured": False,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("105.00"), "ws_price": Decimal("80.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("200.00"), "ws_price": Decimal("155.00"), "moq": 10},
        ]
    },
    {
        "name": "Thattai Vada (Crispy Lentil Discs)",
        "slug": "thattai-vada",
        "category_slug": "traditional-snacks",
        "short_description": "Thin flat crispy rice discs embedded with chana dal, curry leaves, and crushed pepper.",
        "description": "Thin, brittle savoury discs with an earthy aroma of soaked Bengal gram and curry leaves embedded right into the crisp rice batter.",
        "ingredients": "Rice Flour, Urad Dal, Chana Dal (Bengal Gram), Red Chilli, Curry Leaves, Butter, Salt, Oil",
        "shelf_life": "60 Days",
        "is_featured": False,
        "variants": [
            {"weight": Decimal("200.00"), "unit": "g", "price": Decimal("95.00"), "ws_price": Decimal("72.00"), "moq": 10},
            {"weight": Decimal("400.00"), "unit": "g", "price": Decimal("180.00"), "ws_price": Decimal("140.00"), "moq": 10},
        ]
    },
]


def populate():
    print("Starting Snacks Map of Kerala population...")
    for item in SNACKS_MAP_DATA:
        category, _ = Category.objects.get_or_create(
            slug=item["category_slug"],
            defaults={"name": item["category_slug"].replace('-', ' ').title(), "is_active": True}
        )

        product, p_created = Product.objects.update_or_create(
            slug=item["slug"],
            defaults={
                "name": item["name"],
                "category": category,
                "short_description": item["short_description"],
                "description": item["description"],
                "ingredients": item["ingredients"],
                "shelf_life": item["shelf_life"],
                "is_active": True,
                "is_featured": item["is_featured"],
            }
        )
        print(f"[{'CREATED' if p_created else 'UPDATED'}] Product: {product.name} ({product.slug})")

        # Create/Update variants
        for v in item["variants"]:
            weight_val = v["weight"]
            unit_val = v["unit"]
            sku = f"ONF-{product.slug.upper()[:10]}-{int(weight_val) if weight_val == int(weight_val) else weight_val}{unit_val.upper()}"
            variant, v_created = ProductVariant.objects.update_or_create(
                product=product,
                package_weight=weight_val,
                package_unit=unit_val,
                defaults={
                    "sku": sku,
                    "price": v["price"],
                    "wholesale_price": v["ws_price"],
                    "minimum_order_quantity": v["moq"],
                    "is_available": True,
                    "is_available_retail": True,
                    "is_available_wholesale": True,
                }
            )

            # Ensure Stock Item exists with healthy stock
            stock, s_created = StockItem.objects.get_or_create(
                variant=variant,
                defaults={
                    "quantity_on_hand": 250,
                    "reserved_quantity": 0,
                    "low_stock_threshold": 20,
                }
            )
            if not s_created and stock.quantity_on_hand == 0:
                stock.quantity_on_hand = 250
                stock.save()

    print("\nSuccessfully populated all 17 Kerala Snack Map products with variants and inventory!")


if __name__ == "__main__":
    populate()
