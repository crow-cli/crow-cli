//! Coolname generator — ported from Python coolname package.
//! Generates 4-word slugs like "honest-splendid-tarantula-of-fruition".

use rand::Rng;

static ADJECTIVE: &[&str] = &[
    "acrid", "ambrosial", "amorphous", "armored", "aromatic", "bald", "blazing", "boisterous",
    "bouncy", "brawny", "broad", "bulky", "camouflaged", "caped", "chubby", "curvy",
    "elastic", "ethereal", "fat", "feathered", "fiery", "flashy", "flat", "fluffy",
    "foamy", "fragrant", "furry", "fuzzy", "glaring", "hairy", "heavy", "hissing",
    "horned", "icy", "imaginary", "invisible", "lean", "loud", "loutish", "luminous",
    "lumpy", "lush", "masked", "meaty", "messy", "misty", "nebulous", "noisy",
    "nondescript", "organic", "purring", "quiet", "quirky", "radiant", "roaring", "ruddy",
    "rustling", "screeching", "shaggy", "shapeless", "shiny", "silent", "silky", "singing",
    "skinny", "smooth", "soft", "spicy", "spiked", "statuesque", "sticky", "tacky",
    "tall", "tangible", "tentacled", "thick", "thundering", "venomous", "warm", "weightless",
    "whispering", "winged", "wooden", "adorable", "admirable", "affable", "amazing", "amiable",
    "attractive", "beautiful", "calm", "casual", "charming", "cherubic", "classic", "classy",
    "convivial", "cordial", "cuddly", "curly", "cute", "debonair", "easygoing", "elegant",
    "famous", "fresh", "friendly", "funny", "gorgeous", "graceful", "gracious", "gregarious",
    "grinning", "handsome", "healthy", "hilarious", "hot", "interesting", "kind", "laughing",
    "likable", "lovely", "meek", "mellow", "merciful", "neat", "nifty", "noble",
    "notorious", "poetic", "popular", "pretty", "refined", "refreshing", "sexy", "smiling",
    "sociable", "spiffy", "stylish", "supportive", "sweet", "tactful", "whimsical", "abiding",
    "accurate", "adamant", "adaptable", "adventurous", "aggressive", "alluring", "aloof", "ambitious",
    "amusing", "annoying", "arrogant", "aspiring", "audacious", "belligerent", "benign", "berserk",
    "benevolent", "bold", "brave", "cheerful", "chirpy", "cocky", "congenial", "courageous",
    "cryptic", "curious", "daft", "dainty", "daring", "defiant", "delicate", "delightful",
    "determined", "devout", "didactic", "diligent", "discreet", "dramatic", "dynamic", "eager",
    "eccentric", "ecstatic", "effective", "elated", "emotional", "encouraging", "enigmatic", "enthusiastic",
    "evasive", "faithful", "fair", "fanatic", "fearless", "fervent", "festive", "fierce",
    "fine", "free", "furious", "gabby", "garrulous", "gay", "generous", "gentle",
    "girlish", "gleeful", "glistening", "grateful", "greedy", "grumpy", "happy", "honorable",
    "honest", "hopeful", "hospitable", "humble", "humorous", "impetuous", "independent", "industrious",
    "innocent", "intrepid", "jolly", "jovial", "just", "lively", "loose", "loyal",
    "merry", "modest", "mysterious", "nice", "obedient", "optimistic", "orthodox", "outgoing",
    "outrageous", "overjoyed", "passionate", "perky", "placid", "polite", "positive", "proud",
    "prudent", "puzzling", "quixotic", "quizzical", "rebel", "relaxed", "reliable", "resolute",
    "rampant", "righteous", "romantic", "rough", "rousing", "sarcastic", "sassy", "satisfied",
    "sly", "sincere", "snobbish", "solemn", "spirited", "spry", "stalwart", "stirring",
    "swinging", "sympathetic", "talkative", "tasteful", "terrific", "thankful", "tidy", "tremendous",
    "truthful", "unbreakable", "unselfish", "upbeat", "uppish", "valiant", "vehement", "vengeful",
    "vigorous", "vivacious", "vociferous", "zealous", "zippy", "able", "adept", "analytic",
    "astute", "attentive", "brainy", "busy", "calculating", "capable", "careful", "cautious",
    "certain", "chivalrous", "clever", "competent", "conscious", "cooperative", "crafty", "crazy",
    "cunning", "daffy", "devious", "discerning", "efficient", "expert", "functional", "gifted",
    "helpful", "enlightened", "idealistic", "impartial", "industrious", "ingenious", "inquisitive", "inscrutable",
    "intelligent", "inventive", "judicious", "keen", "knowing", "literate", "logical", "masterful",
    "mindful", "nonchalant", "objective", "observant", "omniscient", "poised", "practical", "pragmatic",
    "prodigious", "proficient", "provocative", "qualified", "radical", "rational", "realistic", "reasonable",
    "responsible", "resourceful", "savvy", "sceptical", "sensible", "serious", "shrewd", "skilled",
    "slick", "slim", "sloppy", "smart", "sophisticated", "stoic", "subtle", "succinct",
    "talented", "thoughtful", "tricky", "unbiased", "uptight", "versatile", "versed", "visionary",
    "wise", "witty", "accelerated", "active", "agile", "athletic", "dashing", "deft",
    "dexterous", "durable", "energetic", "fast", "flexible", "formidable", "frisky", "hasty",
    "hypersonic", "meteoric", "mighty", "muscular", "nimble", "nippy", "powerful", "prompt",
    "quick", "rapid", "resilient", "robust", "rugged", "solid", "speedy", "steadfast",
    "steady", "strong", "sturdy", "tireless", "tough", "unyielding", "influential", "rich",
    "venerable", "wealthy", "meticulous", "precise", "rigorous", "scrupulous", "strict", "airborne",
    "burrowing", "crouching", "flying", "hidden", "hopping", "jumping", "lurking", "tunneling",
    "warping", "aboriginal", "amphibian", "aquatic", "arboreal", "celestial", "international", "polar",
    "terrestrial", "urban", "accomplished", "astonishing", "advanced", "authentic", "awesome", "delectable",
    "excellent", "exotic", "exuberant", "fabulous", "fantastic", "fascinating", "flawless", "fortunate",
    "funky", "godlike", "glorious", "groovy", "honored", "illustrious", "imperious", "imposing",
    "important", "impressive", "incredible", "infallible", "invaluable", "kickass", "legendary", "lucky",
    "majestic", "magnificent", "marvellous", "miraculous", "monumental", "perfect", "phenomenal", "pompous",
    "precious", "premium", "private", "remarkable", "spectacular", "splendid", "successful", "wonderful",
    "wondrous", "offbeat", "original", "outstanding", "quaint", "unique", "ancient", "antique",
    "modern", "prehistoric", "primitive", "abstract", "academic", "acoustic", "angelic", "arcane",
    "archetypal", "artificial", "augmented", "auspicious", "automatic", "axiomatic", "beneficial", "bipedal",
    "bizarre", "comical", "complex", "controversial", "dancing", "dangerous", "demonic", "divergent",
    "economic", "educational", "electric", "electronic", "elfish", "elite", "elusive", "eminent",
    "enchanted", "esoteric", "essential", "exceptional", "expensive", "favorite", "fictional", "finicky",
    "fractal", "futuristic", "gainful", "hallowed", "heavenly", "heretic", "holistic", "hungry",
    "hypnotic", "hysterical", "illegal", "immortal", "imperial", "imported", "impossible", "indefinable",
    "inescapable", "invincible", "juicy", "liberal", "ludicrous", "lyrical", "magnetic", "manipulative",
    "mature", "military", "macho", "married", "melodic", "memorable", "musical", "mystic",
    "native", "natural", "naughty", "nocturnal", "normal", "nostalgic", "optimal", "ordinary",
    "pastoral", "peculiar", "piquant", "predictable", "pristine", "prophetic", "psychedelic", "quantum",
    "rare", "real", "secret", "significant", "simple", "spectral", "spiritual", "stereotyped",
    "stimulating", "straight", "strange", "strategic", "tested", "therapeutic", "traditional", "true",
    "ubiquitous", "unbeatable", "uncovered", "undetectable", "unnatural", "unstoppable", "utopian", "vagabond",
    "vague", "vegan", "victorious", "vigilant", "voracious", "wakeful", "wandering", "watchful",
    "wild", "worthy", "bright", "brilliant", "colorful", "crystal", "dark", "dazzling",
    "fluorescent", "glittering", "glossy", "gleaming", "light", "mottled", "neon", "opalescent",
    "pastel", "smoky", "sparkling", "spotted", "striped", "translucent", "transparent", "vivid",
];

static ADJECTIVE_FIRST: &[&str] = &[
    "first", "new",
];

static ADJECTIVE_NEAR: &[&str] = &[
    "almond", "amaranth", "amigurumi", "apricot", "artichoke", "auburn", "azure", "banana",
    "beige", "black", "blond", "blue", "brown", "burgundy", "carmine", "carrot",
    "celadon", "cerise", "cerulean", "charcoal", "cherry", "chestnut", "chocolate", "cinnamon",
    "copper", "cream", "crimson", "cyan", "daffodil", "dandelion", "denim", "ebony",
    "eggplant", "gray", "ginger", "green", "indigo", "infrared", "jasmine", "khaki",
    "lavender", "lilac", "mauve", "magenta", "mahogany", "maize", "marigold", "mustard",
    "ochre", "orange", "origami", "papaya", "paper", "peach", "persimmon", "pink",
    "pistachio", "pumpkin", "purple", "raspberry", "red", "rose", "russet", "saffron",
    "sage", "scarlet", "sepia", "silver", "tan", "tangerine", "taupe", "teal",
    "tomato", "turquoise", "tuscan", "ultramarine", "ultraviolet", "umber", "vanilla", "vermilion",
    "violet", "viridian", "white", "wine", "wisteria", "yellow", "agate", "amber",
    "amethyst", "alchemical", "aquamarine", "asparagus", "beryl", "brass", "bronze", "clay",
    "cobalt", "coral", "cornflower", "diamond", "emerald", "garnet", "golden", "granite",
    "iron", "ivory", "jade", "jasper", "lemon", "lime", "malachite", "marble",
    "maroon", "metal", "myrtle", "nickel", "olive", "olivine", "onyx", "opal",
    "orchid", "pearl", "peridot", "platinum", "porcelain", "quartz", "ruby", "sandy",
    "sapphire", "steel", "thistle", "topaz", "tourmaline", "tungsten", "xanthic", "zircon",
];

static NOUN_ADJECTIVE: &[&str] = &[
    "fancy", "magic", "rainbow", "woodoo",
];

static PREFIX: &[&str] = &[
    "giga", "mega", "micro", "mini", "nano", "pygmy", "super", "uber",
    "ultra", "cyber", "mutant", "ninja", "space",
];

static SIZE: &[&str] = &[
    "big", "colossal", "enormous", "gigantic", "great", "huge", "hulking", "humongous",
    "large", "little", "massive", "miniature", "petite", "portable", "small", "tiny",
    "towering",
];

static ANIMAL: &[&str] = &[
    "earthworm", "leech", "worm", "scorpion", "spider", "tarantula", "barnacle", "crab",
    "crayfish", "lobster", "pillbug", "prawn", "shrimp", "ant", "bee", "beetle",
    "bug", "bumblebee", "butterfly", "caterpillar", "cicada", "cricket", "dragonfly", "earwig",
    "firefly", "grasshopper", "honeybee", "hornet", "inchworm", "ladybug", "locust", "mantis",
    "mayfly", "mosquito", "moth", "sawfly", "silkworm", "termite", "wasp", "woodlouse",
    "centipede", "millipede", "pronghorn", "antelope", "bison", "buffalo", "bull", "chamois",
    "cow", "gazelle", "gaur", "goat", "ibex", "impala", "kudu", "markhor",
    "mouflon", "muskox", "nyala", "oryx", "sheep", "wildebeest", "yak", "zebu",
    "alpaca", "camel", "llama", "vicugna", "caribou", "chital", "deer", "elk",
    "moose", "pudu", "reindeer", "sambar", "wapiti", "beluga", "dolphin", "narwhal",
    "orca", "porpoise", "whale", "donkey", "horse", "stallion", "zebra", "giraffe",
    "okapi", "hippo", "rhino", "boar", "hog", "pig", "swine", "warthog",
    "peccary", "buzzard", "eagle", "goshawk", "harrier", "hawk", "raptor", "vulture",
    "duck", "goose", "swan", "teal", "bird", "hummingbird", "swift", "kiwi",
    "bittern", "potoo", "seriema", "cassowary", "emu", "condor", "auk", "avocet",
    "guillemot", "kittiwake", "puffin", "seagull", "skua", "stork", "dodo", "dove",
    "pigeon", "kingfisher", "tody", "bustard", "coua", "coucal", "cuckoo", "koel",
    "malkoha", "roadrunner", "kagu", "caracara", "falcon", "kestrel", "chachalaca", "chicken",
    "curassow", "grouse", "guan", "junglefowl", "partridge", "peacock", "pheasant", "quail",
    "rooster", "turkey", "loon", "coot", "crane", "turaco", "hoatzin", "bullfinch",
    "crow", "jackdaw", "jaybird", "finch", "lyrebird", "magpie", "myna", "nightingale",
    "nuthatch", "oriole", "oxpecker", "raven", "robin", "rook", "skylark", "sparrow",
    "starling", "swallow", "waxbill", "wren", "heron", "ibis", "jacamar", "piculet",
    "toucan", "toucanet", "woodpecker", "flamingo", "grebe", "albatross", "fulmar", "petrel",
    "spoonbill", "ara", "cockatoo", "kakapo", "lorikeet", "macaw", "parakeet", "parrot",
    "penguin", "ostrich", "boobook", "owl", "booby", "cormorant", "frigatebird", "pelican",
    "quetzal", "trogon", "axolotl", "bullfrog", "frog", "newt", "salamander", "toad",
    "angelfish", "barracuda", "carp", "catfish", "dogfish", "goldfish", "guppy", "eel",
    "flounder", "herring", "lionfish", "mackerel", "oarfish", "perch", "salmon", "seahorse",
    "sturgeon", "sunfish", "tench", "trout", "tuna", "wrasse", "sawfish", "shark",
    "stingray", "jellyfish", "alligator", "caiman", "crocodile", "gharial", "starfish", "urchin",
    "hedgehog", "coyote", "dingo", "dog", "fennec", "fox", "hound", "jackal",
    "tanuki", "wolf", "bobcat", "caracal", "cat", "cougar", "jaguar", "jaguarundi",
    "leopard", "lion", "lynx", "manul", "ocelot", "panther", "puma", "serval",
    "smilodon", "tiger", "wildcat", "aardwolf", "binturong", "cheetah", "civet", "fossa",
    "hyena", "meerkat", "mongoose", "badger", "coati", "ermine", "ferret", "marten",
    "mink", "otter", "polecat", "skunk", "stoat", "weasel", "wolverine", "seal",
    "walrus", "raccoon", "ringtail", "bear", "panda", "bat", "armadillo", "elephant",
    "mammoth", "mastodon", "mole", "hyrax", "bandicoot", "bettong", "cuscus", "kangaroo",
    "koala", "numbat", "quokka", "quoll", "wallaby", "wombat", "echidna", "platypus",
    "tapir", "anteater", "sloth", "agouti", "beaver", "capybara", "chinchilla", "chipmunk",
    "degu", "dormouse", "gerbil", "gopher", "groundhog", "jackrabbit", "jerboa", "hamster",
    "hare", "lemming", "marmot", "mouse", "muskrat", "porcupine", "rabbit", "rat",
    "squirrel", "vole", "ape", "baboon", "bonobo", "capuchin", "chimpanzee", "galago",
    "gibbon", "gorilla", "lemur", "loris", "macaque", "mandrill", "marmoset", "monkey",
    "orangutan", "tamarin", "tarsier", "uakari", "dugong", "manatee", "shrew", "aardwark",
    "clam", "cockle", "mussel", "oyster", "scallop", "shellfish", "ammonite", "cuttlefish",
    "nautilus", "octopus", "squid", "limpet", "slug", "snail", "sponge", "tuatara",
    "agama", "chameleon", "dragon", "gecko", "iguana", "lizard", "pogona", "skink",
    "adder", "anaconda", "asp", "boa", "cobra", "copperhead", "mamba", "python",
    "rattlesnake", "sidewinder", "snake", "taipan", "viper", "tortoise", "turtle", "dinosaur",
    "velociraptor", "mushroom",
];

static ANIMAL_BREED: &[&str] = &[
    "beagle", "bloodhound", "bulldog", "bullmastiff", "chihuahua", "chowchow", "collie", "corgi",
    "dalmatian", "dachshund", "doberman", "foxhound", "husky", "labradoodle", "labrador", "mastiff",
    "malamute", "mongrel", "poodle", "pug", "rottweiler", "saluki", "spaniel", "terrier",
    "whippet", "mule", "mustang", "pony",
];

static ANIMAL_LEGENDARY: &[&str] = &[
    "basilisk", "chimera", "chupacabra", "cockatrice", "dragon", "griffin", "hippogriff", "jackalope",
    "kelpie", "kraken", "manticore", "pegasus", "phoenix", "serpent", "unicorn", "wyvern",
];

static OF_NOUN: &[&str] = &[
    "anger", "bliss", "contentment", "courage", "ecstasy", "excitement", "faith", "felicity",
    "fury", "gaiety", "glee", "glory", "greatness", "inspiration", "jest", "joy",
    "happiness", "holiness", "love", "merriment", "passion", "patience", "peace", "persistence",
    "pleasure", "pride", "recreation", "relaxation", "romance", "serenity", "tranquility", "apotheosis",
    "chaos", "energy", "essence", "eternity", "excellence", "experience", "freedom", "nirvana",
    "order", "perfection", "spirit", "variation", "acceptance", "brotherhood", "criticism", "culture",
    "discourse", "discussion", "justice", "piety", "respect", "security", "support", "tolerance",
    "trust", "warranty", "abundance", "admiration", "assurance", "authority", "awe", "certainty",
    "control", "domination", "enterprise", "fame", "grandeur", "influence", "luxury", "management",
    "opposition", "plenty", "popularity", "prestige", "prosperity", "reputation", "reverence", "reward",
    "superiority", "triumph", "wealth", "acumen", "aptitude", "art", "artistry", "competence",
    "efficiency", "expertise", "finesse", "genius", "leadership", "perception", "skill", "virtuosity",
    "argument", "debate", "action", "agility", "amplitude", "attack", "charisma", "chivalry",
    "defense", "defiance", "devotion", "dignity", "endurance", "exercise", "force", "fortitude",
    "gallantry", "health", "honor", "infinity", "inquire", "intensity", "luck", "mastery",
    "might", "opportunity", "penetration", "performance", "pluck", "potency", "protection", "prowess",
    "resistance", "serendipity", "speed", "stamina", "strength", "swiftness", "temperance", "tenacity",
    "valor", "vigor", "vitality", "will", "advance", "conversion", "correction", "development",
    "diversity", "elevation", "enhancement", "enrichment", "enthusiasm", "focus", "fruition", "growth",
    "improvement", "innovation", "modernism", "novelty", "proficiency", "progress", "promotion", "realization",
    "refinement", "renovation", "revolution", "success", "tempering", "upgrade", "ampleness", "completion",
    "satiation", "saturation", "sufficiency", "vastness", "wholeness", "attraction", "beauty", "bloom",
    "cleaning", "courtesy", "glamour", "elegance", "fascination", "kindness", "joviality", "politeness",
    "refinement", "symmetry", "sympathy", "tact", "calibration", "drama", "economy", "engineering",
    "examination", "philosophy", "poetry", "research", "science", "democracy", "election", "feminism",
    "champagne", "coffee", "cookies", "flowers", "fragrance", "honeydew", "music", "pizza",
    "aurora", "blizzard", "current", "dew", "downpour", "drizzle", "hail", "hurricane",
    "lightning", "rain", "snow", "storm", "sunshine", "tempest", "thunder", "tornado",
    "typhoon", "weather", "wind", "whirlwind", "abracadabra", "adventure", "atheism", "camouflage",
    "destiny", "endeavor", "expression", "fantasy", "fertility", "imagination", "karma", "masquerade",
    "maturity", "radiance", "shopping", "sorcery", "unity", "witchcraft", "wizardry", "wonder",
    "youth", "purring",
];

static OF_NOUN_NO_MOD: &[&str] = &[
    "biology", "chemistry", "education", "experiment", "mathematics", "psychology", "reading", "zoology",
    "cubism", "painting", "advertising", "agreement", "climate", "competition", "effort", "emphasis",
    "forgiveness", "foundation", "judgment", "memory", "opportunity", "perspective", "priority", "promise",
    "teaching",
];

static OF_MODIFIER: &[&str] = &[
    "absolute", "abstract", "algebraic", "amazing", "amusing", "ancient", "angelic", "astonishing",
    "authentic", "awesome", "beautiful", "classic", "delightful", "demonic", "desirable", "easy",
    "eminent", "enjoyable", "eternal", "excellent", "exotic", "extreme", "fabulous", "famous",
    "fantastic", "fascinating", "flawless", "fortunate", "glorious", "good", "great", "heavenly",
    "historical", "holistic", "hypothetical", "ideal", "illegal", "imaginary", "immense", "imminent",
    "impossible", "impressive", "improbable", "incredible", "inescapable", "inevitable", "infinite", "inspiring",
    "interesting", "legal", "legendary", "lucky", "magic", "majestic", "major", "marvelous",
    "massive", "mysterious", "noble", "nonconcrete", "nonstop", "normal", "luxurious", "necessary",
    "objective", "optimal", "original", "pastoral", "perfect", "perpetual", "phenomenal", "pleasurable",
    "pragmatic", "premium", "radical", "rampant", "regular", "remarkable", "satisfying", "serious",
    "scientific", "sexy", "sheer", "significant", "simple", "silent", "spectacular", "splendid",
    "stereotyped", "stimulating", "strange", "striking", "strongest", "sublime", "subtle", "sudden",
    "sufficient", "terrific", "theoretical", "therapeutic", "total", "ultimate", "uncanny", "undeniable",
    "unearthly", "unexpected", "unknown", "unmatched", "unmistakable", "unnatural", "unprecedented", "unreal",
    "unusual", "uplifting", "utter", "weird", "wonderful", "wondrous",
];

static FROM_NOUN_NO_MOD: &[&str] = &[
    "venus", "mars", "jupiter", "ganymede", "saturn", "uranus", "neptune", "pluto",
    "betelgeuse", "sirius", "vega", "arcadia", "asgard", "atlantis", "avalon", "camelot",
    "eldorado", "heaven", "hell", "hyperborea", "lemuria", "nibiru", "shambhala", "tartarus",
    "valhalla", "wonderland",
];

static _FROM2: &[&str] = &[
];

static _SUBJ2: &[&str] = &[
];

/// Generate a 4-word coolname slug.
pub fn generate_slug() -> String {
    let mut rng = rand::rng();
    let af = adj_far();
    let an = adj_near();
    let aa = adj_any();
    let sb = subj();
    let oa = of_noun_any();
    let pattern = rng.random_range(0..8);
    let words: Vec<&str> = match pattern {
        0..=3 => vec![
            pick(&mut rng, &af),
            pick(&mut rng, &an),
            pick(&mut rng, &sb),
            "of",
            pick(&mut rng, &oa),
        ],
        4..=5 => vec![
            pick(&mut rng, &af),
            pick(&mut rng, &an),
            pick(&mut rng, &sb),
            "from",
            pick(&mut rng, FROM_NOUN_NO_MOD),
        ],
        _ => vec![
            pick(&mut rng, &aa),
            pick(&mut rng, &sb),
            "of",
            pick(&mut rng, OF_MODIFIER),
            pick(&mut rng, OF_NOUN),
        ],
    };
    words.join("-")
}

fn pick<'a>(rng: &mut impl Rng, list: &'a [&'a str]) -> &'a str {
    list[rng.random_range(0..list.len())]
}

fn adj_far() -> Vec<&'static str> {
    let mut v = Vec::new();
    v.extend_from_slice(ADJECTIVE);
    v.extend_from_slice(ADJECTIVE_FIRST);
    v.extend_from_slice(NOUN_ADJECTIVE);
    v.extend_from_slice(SIZE);
    v
}

fn adj_near() -> Vec<&'static str> {
    let mut v = Vec::new();
    v.extend_from_slice(ADJECTIVE);
    v.extend_from_slice(ADJECTIVE_NEAR);
    v.extend_from_slice(NOUN_ADJECTIVE);
    v.extend_from_slice(PREFIX);
    v
}

fn adj_any() -> Vec<&'static str> {
    let mut v = Vec::new();
    v.extend_from_slice(ADJECTIVE);
    v.extend_from_slice(ADJECTIVE_NEAR);
    v.extend_from_slice(NOUN_ADJECTIVE);
    v.extend_from_slice(PREFIX);
    v.extend_from_slice(SIZE);
    v
}

fn subj() -> Vec<&'static str> {
    let mut v = Vec::new();
    v.extend_from_slice(ANIMAL);
    v.extend_from_slice(ANIMAL_BREED);
    v.extend_from_slice(ANIMAL_LEGENDARY);
    v
}

fn of_noun_any() -> Vec<&'static str> {
    let mut v = Vec::new();
    v.extend_from_slice(OF_NOUN);
    v.extend_from_slice(OF_NOUN_NO_MOD);
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_four_word_slug() {
        let slug = generate_slug();
        let parts: Vec<&str> = slug.split('-').collect();
        assert!(parts.len() >= 3, "slug should have at least 3 words: {slug}");
        assert!(parts.len() <= 5, "slug should have at most 5 words: {slug}");
    }

    #[test]
    fn slugs_are_unique() {
        let a = generate_slug();
        let b = generate_slug();
        // Technically could collide but astronomically unlikely
        assert_ne!(a, b, "two slugs should differ");
    }

    #[test]
    fn slug_is_lowercase_and_hyphenated() {
        for _ in 0..20 {
            let slug = generate_slug();
            assert!(slug.chars().all(|c| c.is_ascii_lowercase() || c == '-'),
                "slug should be lowercase+hyphens: {slug}");
            assert!(!slug.starts_with('-'));
            assert!(!slug.ends_with('-'));
        }
    }
}
