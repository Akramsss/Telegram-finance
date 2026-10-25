"""Student budget categories, default monthly budgets and keyword rules.

The Budgets tab in the Google Sheet is the source of truth for budget amounts
once the sheet is built; the numbers here are only the starting defaults.
"""

# (name, emoji, default monthly budget in €, subcategories)
EXPENSE_CATEGORIES = [
    ("Groceries", "🛒", 100, [
        "Fruits & Vegetables", "Meat, Poultry & Fish", "Dairy & Eggs",
        "Bread & Grains", "Pantry Staples", "Frozen Food", "Snacks & Sweets", "Drinks",
    ]),
    ("Eating Out", "🍽️", 25, [
        "CROUS / University", "Fast Food", "Restaurant", "Café & Bakery", "Delivery",
    ]),
    ("Housing", "🏠", 0, [
        "Rent", "Electricity & Gas", "Water", "Internet", "Home Insurance",
    ]),
    ("Transport", "🚌", 15, [
        "Transport Pass", "Tickets", "Train & Coach", "Bike & Scooter", "Taxi & Ride-hailing",
    ]),
    ("Studies", "📚", 5, [
        "Books", "Stationery & Supplies", "Printing", "Tuition & Fees", "Software & Courses",
    ]),
    ("Phone & Subscriptions", "📱", 10, [
        "Phone Plan", "Streaming", "Music", "Cloud & Apps",
    ]),
    ("Health & Care", "🧴", 10, [
        "Hygiene & Toiletries", "Pharmacy", "Doctor & Dentist", "Haircut", "Health Insurance",
    ]),
    ("Household", "🧹", 10, [
        "Cleaning Supplies", "Laundry", "Kitchen & Home Items",
    ]),
    ("Clothing", "👕", 5, [
        "Clothes", "Shoes", "Accessories",
    ]),
    ("Leisure", "🎉", 15, [
        "Going Out", "Sport & Gym", "Hobbies", "Events & Tickets", "Gifts",
    ]),
    ("Travel", "✈️", 0, [
        "Travel Transport", "Accommodation", "Activities",
    ]),
    ("Admin & Fees", "🧾", 0, [
        "Bank Fees", "Visa & Residence Permit", "Insurance", "Taxes & Stamps",
    ]),
    ("Other", "📦", 5, [
        "Other",
    ]),
]

INCOME_CATEGORIES = [
    ("CAF / APL", "🏛️", ["Housing Aid"]),
    ("Scholarship", "🎓", ["Scholarship"]),
    ("Family", "👪", ["Family Support"]),
    ("Job", "💼", ["Salary", "Freelance"]),
    ("Other Income", "💶", ["Refund", "Sale", "Other"]),
]

PAYMENT_METHODS = ["Card", "Cash", "Other"]

CATEGORY_NAMES = [c[0] for c in EXPENSE_CATEGORIES]
INCOME_NAMES = [c[0] for c in INCOME_CATEGORIES]
EMOJI = {c[0]: c[1] for c in EXPENSE_CATEGORIES} | {c[0]: c[1] for c in INCOME_CATEGORIES}
SUBCATEGORIES = {c[0]: c[3] for c in EXPENSE_CATEGORIES} | {c[0]: c[2] for c in INCOME_CATEGORIES}
DEFAULT_BUDGETS = {c[0]: c[2] for c in EXPENSE_CATEGORIES}


def label(category: str) -> str:
    return f"{EMOJI.get(category, '•')} {category}"


def valid_subcategory(category: str, sub: str) -> str:
    subs = SUBCATEGORIES.get(category, ["Other"])
    for s in subs:
        if s.lower() == (sub or "").lower():
            return s
    return subs[0]


# Keyword → (category, subcategory). English and French, matched as whole
# words or word prefixes against the lower-cased item text.
KEYWORDS = {
    # Groceries
    ("Groceries", "Fruits & Vegetables"): [
        "apple", "banana", "orange", "fruit", "vegetable", "veg", "tomato", "potato", "onion",
        "carrot", "salad", "lettuce", "cucumber", "pepper", "lemon", "avocado", "grape",
        "strawberr", "pear", "mango", "garlic", "spinach", "courgette", "zucchini", "mushroom",
        "pomme", "banane", "légume", "legume", "tomate", "patate", "oignon", "carotte",
        "concombre", "poivron", "citron", "avocat", "raisin", "fraise", "poire", "ail",
        "champignon", "dattes", "dates", "herbs", "coriander", "parsley", "persil", "coriandre",
    ],
    ("Groceries", "Meat, Poultry & Fish"): [
        "meat", "chicken", "beef", "lamb", "turkey", "fish", "salmon", "tuna", "mince",
        "steak", "sausage", "merguez", "halal", "viande", "poulet", "boeuf", "bœuf", "agneau",
        "dinde", "poisson", "saumon", "thon", "haché", "hache", "kefta", "escalope",
    ],
    ("Groceries", "Dairy & Eggs"): [
        "milk", "egg", "cheese", "yogurt", "yoghurt", "butter", "cream", "lait", "oeuf",
        "œuf", "fromage", "yaourt", "beurre", "crème", "creme", "skyr", "lben",
    ],
    ("Groceries", "Bread & Grains"): [
        "bread", "baguette", "rice", "pasta", "flour", "couscous", "oats", "cereal", "wrap",
        "tortilla", "pain", "riz", "pâtes", "pates", "farine", "semoule", "céréale", "cereale",
        "flocons", "msemen", "brioche",
    ],
    ("Groceries", "Pantry Staples"): [
        "oil", "sugar", "salt", "spice", "sauce", "tomato paste", "lentil", "chickpea", "beans",
        "honey", "jam", "coffee", "tea", "huile", "sucre", "sel", "épice", "epice", "lentille",
        "pois chiche", "haricot", "miel", "confiture", "café", "thé", "the vert", "ketchup",
        "mayo", "mustard", "moutarde", "vinegar", "vinaigre", "conserve", "can ",
        "groceries", "courses", "supermarket", "supermarché",
    ],
    ("Groceries", "Frozen Food"): ["frozen", "surgelé", "surgele", "ice cream", "glace", "pizza surgel"],
    ("Groceries", "Snacks & Sweets"): [
        "chocolate", "chips", "crisps", "biscuit", "cookie", "candy", "snack", "cake",
        "chocolat", "gâteau", "gateau", "bonbon", "nutella", "nuts", "noix", "cacahuète",
    ],
    ("Groceries", "Drinks"): [
        "water", "juice", "soda", "coke", "cola", "drink", "eau", "jus", "boisson", "lemonade",
    ],
    # Eating out
    ("Eating Out", "CROUS / University"): ["crous", "resto u", "restau u", "cafeteria", "cafétéria", "canteen", "cantine"],
    ("Eating Out", "Fast Food"): [
        "kebab", "tacos", "burger", "mcdo", "mcdonald", "kfc", "quick", "subway", "fries",
        "frites", "pizza", "sandwich", "panini", "o'tacos", "burger king",
    ],
    ("Eating Out", "Restaurant"): ["restaurant", "resto", "dinner out", "lunch out", "sushi", "brunch"],
    ("Eating Out", "Café & Bakery"): [
        "starbucks", "coffee shop", "croissant", "pain au chocolat", "boulangerie", "bakery",
        "latte", "cappuccino", "espresso", "pastry", "viennoiserie",
    ],
    ("Eating Out", "Delivery"): ["uber eats", "ubereats", "deliveroo", "just eat", "delivery", "livraison"],
    # Housing
    ("Housing", "Rent"): ["rent", "loyer"],
    ("Housing", "Electricity & Gas"): ["electricity", "électricité", "electricite", "edf", "engie", "gas bill", "gaz"],
    ("Housing", "Water"): ["water bill", "facture eau"],
    ("Housing", "Internet"): ["internet", "wifi", "box", "fibre", "fiber"],
    ("Housing", "Home Insurance"): ["home insurance", "assurance habitation"],
    # Transport
    ("Transport", "Transport Pass"): ["navigo", "pass", "abonnement transport", "monthly pass", "imagine r"],
    ("Transport", "Tickets"): ["ticket", "metro", "métro", "bus", "tram", "rer"],
    ("Transport", "Train & Coach"): ["train", "sncf", "tgv", "ouigo", "flixbus", "blablacar", "coach", "ter "],
    ("Transport", "Bike & Scooter"): ["bike", "vélo", "velo", "velib", "vélib", "scooter", "trottinette", "lime"],
    ("Transport", "Taxi & Ride-hailing"): ["uber", "taxi", "bolt", "heetch", "vtc"],
    # Studies
    ("Studies", "Books"): ["book", "livre", "manual", "manuel"],
    ("Studies", "Stationery & Supplies"): [
        "pen", "notebook", "stylo", "cahier", "paper", "papier", "stationery", "calculator",
        "calculatrice", "folder", "classeur", "fourniture",
    ],
    ("Studies", "Printing"): ["print", "impression", "photocop", "copies"],
    ("Studies", "Tuition & Fees"): ["tuition", "frais d'inscription", "inscription", "cvec", "university fee"],
    ("Studies", "Software & Courses"): ["udemy", "coursera", "course", "cours", "software", "logiciel"],
    # Phone & subscriptions
    ("Phone & Subscriptions", "Phone Plan"): ["phone", "forfait", "free mobile", "sosh", "red by sfr", "bouygues", "orange mobile", "recharge"],
    ("Phone & Subscriptions", "Streaming"): ["netflix", "disney", "prime video", "youtube premium", "crunchyroll", "canal+"],
    ("Phone & Subscriptions", "Music"): ["spotify", "deezer", "apple music"],
    ("Phone & Subscriptions", "Cloud & Apps"): ["icloud", "google one", "chatgpt", "claude", "app store", "subscription", "abonnement"],
    # Health & care
    ("Health & Care", "Hygiene & Toiletries"): [
        "shampoo", "soap", "toothpaste", "toothbrush", "deodorant", "shower gel", "razor",
        "shampoing", "savon", "dentifrice", "brosse à dent", "déodorant", "deo", "gel douche",
        "rasoir", "tissue", "mouchoir", "cotton", "coton", "toilet paper", "papier toilette",
    ],
    ("Health & Care", "Pharmacy"): ["pharmacy", "pharmacie", "medicine", "médicament", "medicament", "doliprane", "paracetamol", "vitamin"],
    ("Health & Care", "Doctor & Dentist"): ["doctor", "médecin", "medecin", "dentist", "dentiste", "consultation", "ophtalmo"],
    ("Health & Care", "Haircut"): ["haircut", "barber", "coiffeur", "barbier"],
    ("Health & Care", "Health Insurance"): ["mutuelle", "health insurance"],
    # Household
    ("Household", "Cleaning Supplies"): [
        "detergent", "dish soap", "sponge", "bleach", "cleaning", "trash bag", "bin bag",
        "lessive", "liquide vaisselle", "éponge", "eponge", "javel", "nettoyant", "sac poubelle",
    ],
    ("Household", "Laundry"): ["laundry", "laverie", "washing machine", "pressing"],
    ("Household", "Kitchen & Home Items"): ["pan", "pot", "plate", "cup", "ikea", "action", "poêle", "casserole", "assiette", "tasse", "towel", "serviette"],
    # Clothing
    ("Clothing", "Clothes"): ["shirt", "t-shirt", "jeans", "pants", "jacket", "hoodie", "sweater", "clothes", "vêtement", "vetement", "pull", "veste", "pantalon", "zara", "h&m", "primark", "kiabi", "uniqlo"],
    ("Clothing", "Shoes"): ["shoes", "sneakers", "chaussure", "baskets"],
    ("Clothing", "Accessories"): ["bag", "sac", "belt", "ceinture", "cap", "casquette", "socks", "chaussettes"],
    # Leisure
    ("Leisure", "Going Out"): ["cinema", "cinéma", "movie", "film", "bowling", "bar", "chicha", "shisha"],
    ("Leisure", "Sport & Gym"): ["gym", "basic fit", "basic-fit", "fitness", "sport", "football", "foot", "salle"],
    ("Leisure", "Hobbies"): ["game", "jeu", "steam", "playstation", "xbox", "nintendo", "hobby"],
    ("Leisure", "Events & Tickets"): ["concert", "event", "festival", "museum", "musée", "musee", "match"],
    ("Leisure", "Gifts"): ["gift", "cadeau", "present"],
    # Travel
    ("Travel", "Travel Transport"): ["flight", "plane", "vol ", "avion", "ryanair", "easyjet", "transavia"],
    ("Travel", "Accommodation"): ["hotel", "hôtel", "airbnb", "hostel", "auberge", "booking"],
    # Admin & fees
    ("Admin & Fees", "Bank Fees"): ["bank fee", "frais bancaire", "agios", "commission"],
    ("Admin & Fees", "Visa & Residence Permit"): ["visa", "titre de séjour", "titre de sejour", "ofii", "residence permit", "préfecture", "prefecture"],
    ("Admin & Fees", "Taxes & Stamps"): ["timbre", "stamp", "tax", "impôt", "impot"],
    ("Admin & Fees", "Insurance"): ["insurance", "assurance"],
}

INCOME_KEYWORDS = {
    ("CAF / APL", "Housing Aid"): ["caf", "apl", "aide logement", "housing aid"],
    ("Scholarship", "Scholarship"): ["bourse", "scholarship", "crous bourse", "grant"],
    ("Family", "Family Support"): ["family", "famille", "parents", "dad", "mom", "papa", "maman", "brother", "frère"],
    ("Job", "Salary"): ["salary", "salaire", "paycheck", "job", "work", "paie"],
    ("Job", "Freelance"): ["freelance", "client", "mission"],
    ("Other Income", "Refund"): ["refund", "remboursement", "rembourse"],
    ("Other Income", "Sale"): ["sold", "vendu", "vinted", "leboncoin"],
}

STORES = [
    "lidl", "aldi", "carrefour", "leclerc", "auchan", "intermarché", "intermarche", "monoprix",
    "franprix", "casino", "super u", "hyper u", "netto", "picard", "grand frais", "biocoop",
    "naturalia", "action", "ikea", "decathlon", "amazon", "fnac", "boulanger", "darty",
    "primark", "zara", "h&m", "kiabi", "uniqlo", "pharmacie", "tang frères", "paris store",
]


# Short button labels so three categories fit on one row in Telegram.
SHORT = {
    "Groceries": "Groceries", "Eating Out": "Eating out", "Housing": "Housing",
    "Transport": "Transport", "Studies": "Studies", "Phone & Subscriptions": "Phone & subs",
    "Health & Care": "Health", "Household": "Household", "Clothing": "Clothes",
    "Leisure": "Leisure", "Travel": "Travel", "Admin & Fees": "Admin", "Other": "Other",
    "CAF / APL": "CAF / APL", "Scholarship": "Scholarship", "Family": "Family", "Job": "Job",
    "Other Income": "Other",
}

SUB_EMOJI = {
    "Fruits & Vegetables": "🍎", "Meat, Poultry & Fish": "🍗", "Dairy & Eggs": "🥛",
    "Bread & Grains": "🥖", "Pantry Staples": "🫙", "Frozen Food": "🧊", "Snacks & Sweets": "🍫",
    "Drinks": "🧃",
    "CROUS / University": "🎓", "Fast Food": "🍔", "Restaurant": "🍝", "Café & Bakery": "☕",
    "Delivery": "🛵",
    "Rent": "🔑", "Electricity & Gas": "⚡", "Water": "🚰", "Internet": "🌐", "Home Insurance": "🛡️",
    "Transport Pass": "🎫", "Tickets": "🎟️", "Train & Coach": "🚆", "Bike & Scooter": "🚲",
    "Taxi & Ride-hailing": "🚕",
    "Books": "📖", "Stationery & Supplies": "✏️", "Printing": "🖨️", "Tuition & Fees": "🏫",
    "Software & Courses": "💻",
    "Phone Plan": "📞", "Streaming": "📺", "Music": "🎧", "Cloud & Apps": "☁️",
    "Hygiene & Toiletries": "🧼", "Pharmacy": "💊", "Doctor & Dentist": "🩺", "Haircut": "💈",
    "Health Insurance": "🏥",
    "Cleaning Supplies": "🧽", "Laundry": "🧺", "Kitchen & Home Items": "🍳",
    "Clothes": "👕", "Shoes": "👟", "Accessories": "🎒",
    "Going Out": "🍿", "Sport & Gym": "🏋️", "Hobbies": "🎮", "Events & Tickets": "🎤", "Gifts": "🎁",
    "Travel Transport": "✈️", "Accommodation": "🏨", "Activities": "🗺️",
    "Bank Fees": "🏦", "Visa & Residence Permit": "🛂", "Insurance": "📑", "Taxes & Stamps": "📮",
    "Other": "📦",
    "Housing Aid": "🏛️", "Scholarship": "🎓", "Family Support": "👪", "Salary": "💼",
    "Freelance": "🧑‍💻", "Refund": "↩️", "Sale": "🏷️",
}


def sub_label(sub: str) -> str:
    return f"{SUB_EMOJI.get(sub, '•')} {sub}"
