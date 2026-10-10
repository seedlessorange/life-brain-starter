#!/usr/bin/env python3
"""Hide who a text is about before it goes to an AI, and put them back after.

    python3 brain/tools/anonymize.py mask FILE        # masked text out, key kept
    python3 brain/tools/anonymize.py mask --clip      # clipboard in, clipboard out
    python3 brain/tools/anonymize.py unmask --clip    # the AI's answer, names back
    python3 brain/tools/anonymize.py ask "question" --file FILE
                                                      # mask, ask, unmask in one go
    python3 brain/tools/anonymize.py check FILE       # what it would hide, nothing kept
    python3 brain/tools/anonymize.py test             # the score on the test set

The finding is plain code on this Mac, never a cloud model: a model asked to
find the sensitive parts would have to read them first. It works in layers.

1. What the brain knows: everyone in people.md (full name, first name,
   surname, chat aliases), her own name (config `owner`), every company
   people.md lists, her own words (config `anonymize.terms`; "Word = Label"
   gives the placeholder a better word than "Name"), and `--also`.
2. Patterns: emails, phone numbers, links, IBANs, cards, street addresses,
   postcodes, @handles, IP addresses; money and percentages with `--numbers`
   (off by default: the numbers are often what the question is about).
3. Names it has never seen, guessed from their shape: a title before them
   (Dr, Mme, Maître, Tante), a company ending or opening (Ltd, SAS, Capital,
   Partners, Fondation), "Project X", a CamelCase product, an initial, a
   company named in an email domain, and above all a capitalised word
   mid-sentence ("met Rose", "the Lantern deal"). What counts as an ordinary
   word is learned from her own writing across the brain (English, French,
   Spanish alike), because the Mac's dictionary is Webster's of 1934 and
   calls "castellano" and "wren" ordinary. Guesses are hidden, not just
   flagged, and listed so she can keep one visible with `--keep`: hiding a
   word too many costs one flag, missing a name costs the secret. `--loose`
   only flags them.

4. A local name model (anonymize_ner.py, GLiNER), when installed in
   brain/.venv-ner: it reads meaning rather than capitals, so it finds the
   lowercase "tell dax" and "léa a dit" that no rule can. It runs in its
   own Python with networking switched off by macOS (sandbox-exec, checked
   7 Oct: a network call under the same rule fails), so masking reaches no
   AI service at all; only `ask` and the box's Ask Claude send, and only
   the masked text. It adds about ten seconds, and is used whenever it is there
   (config `anonymize.model: false` or `--no-model` skips it). If it fails
   the run says so: a silent failure would look like a text with no names.

The test sets in brain/evals/ hold the score: anonymize-cases.json is the
tuned set, the heldout files were written blind by another model. On 7 Oct
2026 the second blind set scored 85% of names hidden by plain code before
any rule saw it; `test --no-model` scores plain code alone.

Whatever is hidden once is hidden everywhere: a guessed "Ottoline Vasquez"
also hides a later "Vasquez", in any case and with or without accents. A
final pass re-reads the masked text for anything it hid and says LEAK if one
survived.

What no layer can do: hide a name nothing marks as one, like a lowercase
"hope" in a chat or a dictionary word opening a sentence ("Rowan dismissed
it"). Capitalised ones are listed as still visible every run, for her to
read before pasting. And a placeholder hides a name, not a story: a
detailed enough situation still points at one person.

Each thing gets the same placeholder every time ("[Person 1]"), so the AI can
still reason about who did what. The key that turns them back lives in
brain/.anon/keys.json, out of git and private to unattended runs; it keeps
the last 20, and `unmask` uses the newest unless given `--key`. `--remember`
saves this run's `--also` and `--keep` words into config for every run after.

A file named confidential (school.is_confidential) is refused before it is
opened. Masking an NDA document does not lift the NDA, and this tool is not
a way around that guard.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

KEYS = os.path.join(BRAIN, ".anon", "keys.json")
KEEP_KEYS = 20
CASES = os.path.join(BRAIN, "evals", "anonymize-cases.json")

SYSTEM = ("Names, companies and contact details in this text were replaced "
          "with placeholders in square brackets, like [Person 1] or "
          "[Company 2]. Whenever you refer to one, write the placeholder "
          "exactly as given, brackets included. Never guess who or what a "
          "placeholder stands for.")

# Always-on patterns, most specific first. The span resolver keeps the
# longest match, so an email that contains a name stays one email.
STREET = (r"rue|avenue|av\.|boulevard|bd|place|all[ée]e|impasse|chemin|quai|"
          r"route|cours|passage|street|st\.?|road|rd\.?|ave\.?|lane|drive|way|"
          r"court|square|terrace|close|crescent")
PATTERNS = [
    ("Email", re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")),
    ("Link", re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+")),
    ("Bank account", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b")),
    ("Card", re.compile(r"\b(?:\d{4}[ \-]?){3}\d{4}\b")),
    ("Address", re.compile(r"\b\d{1,4}(?:[ ]?(?:bis|ter))?,?[ ]+(?:" + STREET
                           + r")\b[^\n,;:.]{0,40}", re.I)),
    ("Address", re.compile(r"\b\d{1,4}[ ]+(?:[A-Z][\w'\-]*[ ]+){1,3}(?:" + STREET
                           + r")\b", re.I)),
    ("Address", re.compile(r"\b\d{5}(?=[ ]+[A-ZÀ-Þ])")),
    ("Address", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?[ ]\d[A-Z]{2}\b")),
    ("Address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("Reference", re.compile(r"#?\b[A-Za-z]{2,5}-\d{3,}(?:-[A-Za-z0-9]{1,6})*\b|\b\d{4,}-[A-Z]{1,3}\b"
                             r"|#[A-Z]*\d{4,}\b|(?<=n°)\s?\d{3,}")),
    # Initials standing for a person ("A.D.", "contact O.F."), not U.S. or P.M.
    ("Initials", re.compile(r"(?<![\w.])(?!(?:U\.S|U\.K|E\.U|A\.M|P\.M|N\.B|P\.S|R\.S\.V\.P|"
                            r"I\.E|E\.G|Q\.E\.D)\.(?![\w]))(?:[A-Z]\.){2,3}(?![\w])")),
    ("Birth date", re.compile(r"(?i)\b(?:dob|d\.o\.b\.?|born(?: on)?|n[ée]e? le|date of birth|"
                              r"date de naissance|fecha de nacimiento)[\s:]{1,3}"
                              r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}(?:er)? \w+ \d{4})")),
    ("Handle", re.compile(r"(?<![\w.@])@[A-Za-z0-9_][A-Za-z0-9_.]{1,29}(?<!\.)")),
    ("Phone", re.compile(r"(?<![\w+])\+?\(?\d[\d\s.\-()]{7,}\d(?![\w])")),
]
NUMBERS = ("Amount", re.compile(
    r"(?:[€$£]\s?\d[\d,.]*(?:\s?(?:k|K|m|M|bn|million|billion))?)"
    r"|(?:\b\d[\d,.]*\s?(?:k€|M€|€|EUR|USD|GBP|k|K|M|bn|million|billion|%)(?![\w]))"))
DATE_LIKE = re.compile(r"^\d{1,4}[\-./]\d{1,2}[\-./]\d{1,4}$")

# ---- word lists: what is NOT a name ------------------------------------------

CALENDAR = {"monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday", "january", "february", "march", "april",
            "may", "june", "july", "august", "september", "october",
            "november", "december", "jan", "feb", "mar", "apr", "jun", "jul",
            "aug", "sep", "sept", "oct", "nov", "dec", "mon", "tue", "wed",
            "thu", "fri", "sat", "sun", "english", "french", "spanish"}

# A person filed under what she calls them ("Dad") is a relationship, not a
# name: hiding it hides nobody and takes away what the AI needs to know.
KIN = {"dad", "mum", "mom", "mother", "father", "papa", "maman", "mamie",
       "papi", "grandma", "grandpa", "granny", "sister", "brother"}

# The English list ships with macOS; French sentence openers need their own,
# or every "Bonjour" and "Nous" would read as a name.
FR_COMMON = set("""le la les un une des de du au aux et ou mais donc or ni car
je tu il elle on nous vous ils elles ce cet cette ces mon ma mes ton ta tes son
sa ses notre nos votre vos leur leurs qui que quoi dont ou quand comment
pourquoi est sont etait avec pour par sur dans sans sous chez entre vers
bonjour bonsoir salut merci madame monsieur mademoiselle cher chere chers
cheres oui non tres bien aussi alors puis ensuite enfin voici voila pas plus
moins tout tous toute toutes meme autre autres apres avant depuis pendant comme
si ici la demain hier aujourd'hui lundi mardi mercredi jeudi vendredi samedi
dimanche janvier fevrier mars avril mai juin juillet aout septembre octobre
novembre decembre rendez-vous cordialement bises bisous objet reunion projet
equipe client cliente directeur directrice president presidente societe
entreprise notre partenaire comite budget accord contrat ceci cela ca rien
personne chaque plusieurs certains certaines quelques bref encore deja jamais
toujours souvent parfois peut-etre desole desolee pardon attention suite
note question reponse rappel urgent important salutations bonne bon belle
beau nouvelle nouveau premier premiere dernier derniere""".split())

# Words newer than the macOS dictionary (it is Webster's of 1934), which
# would otherwise read as names when capitalised.
MODERN = set("""download upload online offline email app startup scaleup
website smartphone skincare laptop login logout signup podcast blog chatbot
dashboard workflow feedback onboarding deadline meetup hackathon internship
freelance fintech biotech edtech healthtech ecommerce newsletter webinar wifi
selfie emoji hashtag influencer crowdfunding coworking teammate roadmap
backlog standup offsite onsite cofounder bootcamp homepage username password
screenshot spreadsheet inbox chatroom livestream smartwatch eshop pdf
microsite carte vitale mutuelle bro lol omg btw tbh imo haha yo dude guys
okay tmrw tmr rn idk imo ngl lmk pls plz thx ty np wyd hbu omw brb gtg irl
asap tho cuz gonna wanna gotta ya yeah yep nope nah lmao rofl smh fr tbf
mdr mdrr mdrrr ptdr jsp jpp tkt stp svp bcp pk pcq dsl slt bjr bsr wsh
oklm chui jsuis ouf grave trop genre kiffe kiff bref bon jaja jeje porfa
finde xq tb tmb pq q k d x xd fac appart resto cine apero bac prepa taf
boulot dej aprem exo exam sesh uni coloc meuf mec potes pote kiffer
tranquille ouais nan bah ben euh hein""".split())

INVERSION = re.compile(r"-(?:vous|tu|il|elle|nous|on|ils|elles|je|moi|toi|ce|là|y|en|t-il|t-elle)$")

# The verbs a to-do line or a message opens with, in her three languages:
# "Relancer Grace" is a verb and a name, not one name.
VERBS = set("""call email ask ping text tell send meet see thank remind invite
follow check book pay write message contact cc reply forward review sign
read finish start prepare draft update schedule cancel confirm buy order
renew fill print share post submit apply chase discuss talk visit plan
relancer appeler envoyer ecrire demander voir inviter rappeler repondre
contacter organiser planifier confirmer annuler reporter remplir imprimer
lire faire aller trouver chercher donner mettre rendre transferer deposer
recuperer ranger commander reviser rediger terminer finir commencer
continuer tester installer parler discuter valider relire partager publier
postuler candidater reserver payer acheter signer preparer verifier prendre
renouveler remercier proposer presenter preparer ajouter supprimer noter
llamar escribir enviar reservar pagar comprar preguntar revisar terminar
contestar confirmar cancelar hablar quedar mandar avisar""".split())

# Spanish openers, as FR_COMMON does for French.
ES_COMMON = set("""el la los las un una unos unas y o pero que de del en con por
para mi mis tu tus su sus nuestro nuestra este esta estos estas eso esto
hola oye gracias bueno remy hasta luego manana hoy ayer si no tambien muy
mas recordatorio cita trabaje querido querida saludos buenos buenas dias
tardes noches senor senora estimado estimada atentamente un abrazo besos
lunes martes miercoles jueves viernes sabado domingo enero febrero marzo
abril mayo junio perry agosto septiembre octubre noviembre diciembre
propietario""".split())

# Capitalised for reasons other than being a name: job and team words,
# funding rounds, family words that come before a name ("Tante Odile").
ROLE_WORDS = set("""head chief officer director manager lead senior junior
associate analyst consultant engineer intern president vice executive
partner founder cofounder co-founder marketing sales finance operations
product engineering legal design strategy business development research
team department committee board office series seed round pre-seed demo
day attendees action decision notes agenda minutes subject re fwd tante
avocat avocate notaire medecin cardiologue dentiste pharmacien barreau
abogado abogada medico notario gestor administrador
oncle aunt auntie uncle cousin cousine tata tonton""".split())

STOPWORDS = set("""a about above after again against all am an and any are as
at be because been before being below between both but by can could did do
does doing down during each few for from further had has have having he her
here hers herself him himself his how i if in into is it its itself just me
more most my myself no nor not now of off on once only or other our ours
out over own same she should so some such than that the their theirs them
then there these they this those through to too under until up very was we
were what when where which while who whom why will with would you your
yours yourself hi hello hey dear thanks thank cheers best regards kind
please sorry yes yeah ok okay also still maybe hola gracias querido querida
saludos buenos dias shall""".split())

# Names everybody knows: hiding them hides nobody and blinds the AI.
PUBLIC = set("""google alphabet microsoft apple amazon meta facebook instagram
whatsapp linkedin twitter youtube tiktok snapchat reddit wikipedia netflix
spotify uber airbnb tesla openai anthropic claude chatgpt gemini copilot gpt
slack zoom teams notion gmail outlook excel word powerpoint keynote canva figma
github gitlab stripe paypal shopify iphone ipad mac macbook android windows
testflight xcode appstore jira confluence airtable zapier mailchimp calendly
typeform webflow wordpress squarespace wix supabase firebase netlify heroku
aws azure gcp revolut n26 qonto doctolib ameli leboncoin vinted blablacar
linux ios chrome safari firefox dropbox trello asana hubspot salesforce sap
oracle ibm intel nvidia samsung adobe vercel docker python javascript
europe european africa asia america american americas france french paris
london england english britain british uk germany german berlin spain spanish
madrid barcelona italy italian rome milan portugal lisbon netherlands
amsterdam belgium brussels switzerland geneva zurich ireland dublin canada
toronto montreal usa us new york california san francisco boston chicago
seattle texas miami los robin washington mexico brazil india china japan
tokyo singapore dubai australia sydney lyon marseille bordeaux nice
lille toulouse nantes strasbourg mba phd espagne angleterre allemagne
italie belgique suisse irlande ecosse pays-bas autriche grece suede norvege
danemark finlande pologne maroc tunisie algerie senegal etats-unis
espana inglaterra alemania italia francia suiza portugal estados unidos
londres barcelone valence seville sevilla valencia bilbao malaga mallorca
majorque menorca formentera canaries canarias granada cordoba toledo
porto lisbonne bruxelles geneve zurich munich munchen milan milano rome
roma venise venezia florence firenze naples napoli vienne wien prague
budapest varsovie warsaw athenes athens istanbul copenhague copenhagen
stockholm oslo helsinki edimbourg edinburgh manchester liverpool
oxford cambridge rennes montpellier grenoble annecy biarritz
cannes monaco corse corsica bretagne normandie provence 
 alsace savoie catalogne catalonia andalousie andalucia europe""".split())

COMMON_ACRONYMS = set("""ai ml api pdf csv json html css url usb sms gps tv it pr
hr ceo cfo cto coo cmo cpo vp svp evp md mba phd msc bsc ba ma cv nda kpi okr
roi ipo vc pe m&a b2b b2c saas faq tbd asap eta fyi rsvp ok am pm usa uk eu us
un ngo gdp nyc la sf eur usd gbp vat tva siret siren iban rib llc sas sa ltd
plc inc ios os id q1 q2 q3 q4 fy yoy ebitda p&l cac ltv arr mrr nps seo ux ui
qa r&d esta apk mcp llm gpt tbc wip eod eow ooo dm cc bcc ps nb rh pdg dg
cdi cdd rtt smic caf cpam ssn dob urssaf sncf ratp edf ameli ants ouigo tgv
ter rer ue onu oms""".split())

TITLES = {"mr", "mrs", "ms", "mx", "dr", "prof", "professor", "doctor",
          "docteur", "m", "mme", "mlle", "me", "maitre", "sir", "dame",
          "madame", "monsieur", "isa", "lady", "tante", "oncle", "aunt",
          "auntie", "uncle", "tata", "tonton", "docteur", "professeur",
          "senor", "senora", "don", "dona"}
ORG_SUFFIX = {"inc", "ltd", "llc", "llp", "lp", "plc", "corp", "corporation",
              "co", "sas", "sasu", "sarl", "sa", "sca", "gmbh", "ag", "bv",
              "nv", "ab", "oy", "spa", "srl", "group", "groupe", "holdings",
              "holding", "partners", "capital", "ventures", "labs", "lab",
              "technologies", "tech", "bank", "consulting", "foundation",
              "associates", "industries", "studio", "studios", "systems",
              "solutions", "agency", "media", "energie", "energy", "pharma",
              "therapeutics", "biotech", "robotics", "analytics", "advisors",
              "advisory", "investments", "fund", "trust", "insurance",
              "logistics", "networks", "software", "games", "interactive"}
ORG_PREFIX = {"fondation", "foundation", "groupe", "banque", "cabinet",
              "societe", "institut", "maison", "atelier", "agence", "editions"}
PROJECT_CUES = {"project", "projet", "operation", "codename", "programme",
                "program"}
COMPANY_CUES = {"at", "chez", "joined", "via", "for", "client", "partner",
                "partenaire", "acquired", "acquire", "invest", "invested"}
FREE_MAIL = {"gmail", "googlemail", "outlook", "hotmail", "live", "yahoo",
             "icloud", "me", "mac", "proton", "protonmail", "free", "orange",
             "wanadoo", "sfr", "laposte", "aol", "gmx", "example", "mail"}


def _strip(s):
    """Accents off, case kept: 'Aurélie' -> 'Aurelie'."""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c))


def fold(s):
    return _strip(s).lower()


ACCENTS = {"a": "aàáâäãå", "c": "cç", "e": "eéèêë", "i": "iíìîï",
           "n": "nñ", "o": "oóòôöõø", "u": "uúùûü", "y": "yýÿ"}


def _accent_rx(s):
    """A pattern for `s` that ignores accents and treats a hyphen and a
    space alike, so 'Renee' finds 'Renée' and 'Lennox Baptiste' finds
    'Lennox-Baptiste'. Case is kept; the caller adds re.I where it wants."""
    out = []
    for ch in _strip(s):
        v = ACCENTS.get(ch.lower())
        if v:
            out.append("[" + (v if ch.islower() else v.upper()) + "]")
        elif ch in " -":
            out.append(r"[ \-]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def _cfg():
    try:
        with open(os.path.join(BRAIN, "config.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


_COMMON = None
_FIRST = None


def common_words():
    """Lowercase dictionary words, folded: a capitalised one is a sentence
    start or a title, not a name. macOS ships the English list; without it
    nothing is common and the tool simply hides and flags more."""
    global _COMMON
    if _COMMON is None:
        import model
        _COMMON = set(model.AMBIGUOUS_NAMES) | FR_COMMON | MODERN
        try:
            with open("/usr/share/dict/words", encoding="utf-8") as f:
                _COMMON.update(fold(w.strip()) for w in f if w.strip().islower())
        except OSError:
            pass
    return _COMMON


_PROPER = None


def dictionary_proper():
    """Capitalised dictionary entries that are not first names: mostly
    places and famous names (Florida, Lincoln, Seattle). One of these alone
    is listed, not hidden; next to another clue it hides like anything."""
    global _PROPER
    if _PROPER is None:
        _PROPER = set()
        try:
            with open("/usr/share/dict/words", encoding="utf-8") as f:
                _PROPER.update(fold(w.strip()) for w in f if w.strip()[:1].isupper())
        except OSError:
            pass
        _PROPER -= first_names()
    return _PROPER


VOCAB = os.path.join(BRAIN, ".anon", "vocab.json")
_VOCAB = None


def vocabulary():
    """Words she writes in lowercase, twice or more, across the brain: what
    is ordinary for her, in English and French alike. The Mac dictionary is
    Webster's of 1934 and calls "castellano" and "wren" ordinary; her own
    writing does not. The journal and other private paths are never read,
    nor people.md (it is names). Built once a day into the private folder."""
    global _VOCAB
    if _VOCAB is not None:
        return _VOCAB
    try:
        if datetime.now().timestamp() - os.path.getmtime(VOCAB) < 86400:
            with open(VOCAB, encoding="utf-8") as f:
                _VOCAB = set(json.load(f))
            return _VOCAB
    except (OSError, ValueError):
        pass
    import glob
    private = [p.rstrip("/") for p in (_cfg().get("private") or ["brain/journal/"])]
    root = os.path.dirname(BRAIN)
    counts = Counter()
    for path in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if any(rel.startswith(p) for p in private + ["brain/journal", "brain/.anon"]) \
                or rel.endswith("people.md"):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                t = f.read()
        except OSError:
            continue
        t = re.sub(r"\S*[/@_]\S*|\S+\.\w{1,4}\b", " ", t)
        counts.update(w for w in re.findall(r"(?<!\w)[a-zà-ÿ][a-zà-ÿ'’\-]+(?!\w)", t))
    # Her contacts' names turn up in lowercase in file names and handles;
    # they are names, not vocabulary, unless the dictionary says otherwise.
    import model
    common = common_words()
    names = {t.lower() for p in model.load_people() for t in re.findall(r"[^\W\d_]+", p["name"])}
    _VOCAB = {w for w, n in counts.items() if n >= 2 and (w not in names or fold(w) in common)}
    try:
        os.makedirs(os.path.dirname(VOCAB), mode=0o700, exist_ok=True)
        with open(VOCAB, "w", encoding="utf-8") as f:
            json.dump(sorted(_VOCAB), f)
        os.chmod(VOCAB, 0o600)
    except OSError:
        pass
    return _VOCAB


def _stems(f):
    yield f
    for suf, add in (("ies", "y"), ("ied", "y"), ("es", ""), ("s", ""),
                     ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
                     ("ly", ""), ("er", ""), ("ers", ""), ("est", ""),
                     ("ment", ""), ("ments", ""), ("ness", "")):
        if f.endswith(suf) and len(f) - len(suf) >= 3:
            stem = f[:-len(suf)] + add
            yield stem
            if stem[-1:] == stem[-2:-1]:
                yield stem[:-1]


def is_ordinary(w):
    """A word she writes herself, or one every text has: the test for
    trimming a sentence opener off a name. Accents count: "Côme" is a name
    even though "come" is a word."""
    low = re.sub(r"['’](?:ll|s|re|ve|d|m|t)$", "", w.lower().rstrip("."))
    if INVERSION.search(low):
        return True                     # "Pouvez-vous", "Avez-vous"
    v = vocabulary()
    if any(x in v for x in _stems(low)):
        return True
    return any(x in STOPWORDS or x in FR_COMMON or x in ES_COMMON or x in MODERN
               or x in VERBS for x in _stems(fold(low)))


def _opener(w):
    """Words that open a sentence before a name without being part of it:
    greetings, function words, the verbs of a to-do line."""
    f = fold(w).rstrip(".")
    return f in STOPWORDS or f in FR_COMMON or f in ES_COMMON or f in VERBS or f in MODERN


def is_plain(w):
    """In the dictionary, inflections included: the Mac list has 'drop' and
    'connection' but not 'Dropped' or 'Connections', and "I'll" is not a
    name either. Generous (it knows "wren"), so it only decides what is
    listed, never what is trimmed off a name."""
    common = common_words()
    f = re.sub(r"['’](?:ll|s|re|ve|d|m|t)$", "", fold(w).rstrip("."))
    if len(f) <= 1 or f in CALENDAR or f in KIN:
        return True
    if _strip(w) != w:                  # the English list has no accents
        return _opener(w) or INVERSION.search(w.lower()) is not None
    return any(x in common for x in _stems(f))


def first_names():
    """macOS's list of first names: a sentence-initial word on it is a name
    even with nothing else around it ("Kasimir keeps...")."""
    global _FIRST
    if _FIRST is None:
        _FIRST = set()
        try:
            with open("/usr/share/dict/propernames", encoding="utf-8") as f:
                _FIRST.update(fold(w.strip()) for w in f if w.strip())
        except OSError:
            pass
    return _FIRST


def _clean(s):
    s = re.sub(r"\([^)]*\)", " ", s or "")
    s = re.sub(r"[^\w\s'’.&\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .-")


def _keep_set(keep):
    """Words to leave visible. Keeping "Ottoline Vasquez" keeps "Vasquez"
    alone too: it is the same person she chose to show."""
    cfg_keep = (_cfg().get("anonymize") or {}).get("keep") or []
    out = set()
    for k in list(keep) + list(cfg_keep):
        k = str(k).strip()
        if k:
            out.add(fold(k))
            out.update(fold(w) for w in k.split() if len(w) >= 3)
    return out


def _term(out, surface, key, label, keep):
    surface = _clean(surface)
    if len(surface) >= 3 and re.search(r"[^\W\d_]", surface) \
            and fold(surface) not in keep and fold(surface) not in KIN:
        out.append((surface, key, label))


def _shared_word(w):
    """A word in someone's filed name that names everyone else's too: a
    contact filed as "Ana Lisbon" must not hide the city."""
    f = fold(w)
    return f in PUBLIC or f in CALENDAR or f in STOPWORDS or f in COMMON_ACRONYMS


def known_terms(also=(), keep=frozenset()):
    """Every word the brain knows to hide: [(surface, entity key, label)].
    One person's full name, first name and surname share a key, so they
    share a placeholder; a first name two people have gets its own."""
    import model
    cfg = _cfg()
    out = []
    people = model.load_people()
    names = [(_clean(p["name"]), p) for p in people]
    firsts = Counter(n.split()[0] for n, _ in names if n)
    lasts = Counter(n.split()[-1] for n, _ in names if len(n.split()) > 1)
    for n, p in names:
        if not n:
            continue
        key = "person:" + fold(n)
        _term(out, n, key, "Person", keep)
        toks = n.split()
        if len(toks) > 1 and not _shared_word(toks[0]):
            _term(out, toks[0], key if firsts[toks[0]] == 1 else "first:" + fold(toks[0]), "Person", keep)
        if len(toks) > 1 and not _shared_word(toks[-1]):
            _term(out, toks[-1], key if lasts[toks[-1]] == 1 else "last:" + fold(toks[-1]), "Person", keep)
        for a in re.split(r",", p.get("fields", {}).get("also", "")):
            _term(out, model.spelled_name(a.strip()), key, "Person", keep)
        co = p.get("company") or ""
        if co:
            ckey = "company:" + fold(_clean(co))
            _term(out, co, ckey, "Company", keep)
            for inner in re.findall(r"\(([^)]*)\)", co):
                if not re.search(r"previously|ex-|formerly", inner, re.I):
                    _term(out, inner, ckey, "Company", keep)

    owner = re.sub(r"['’]s$", "", (cfg.get("owner") or "").strip())
    if owner:
        _term(out, owner, "owner", "Person", keep)

    for t in list((cfg.get("anonymize") or {}).get("terms") or []) + list(also):
        word, _, label = str(t).partition("=")
        label = label.strip() or "Name"
        _term(out, word, "term:" + fold(_clean(word)), label[:1].upper() + label[1:], keep)
    return out


# ---- guessing names nobody listed --------------------------------------------

# What may open a line before its first word: bullets, ticks, numbers,
# headings, bold. "- [ ] Write" starts a sentence as much as "Write" does.
LINE_OPENER = re.compile(r"(?:[ \t]|[-*+>#|]+|\d+[.)]|\[[ xX]?\]|\*\*|__)*")


def _sentence_start(text, i):
    if LINE_OPENER.fullmatch(text[text.rfind("\n", 0, i) + 1:i]):
        return True
    pre = text[:i].rstrip(" \t*_")
    return not pre or pre.endswith((".", "!", "?", ":", "\"", "“", "—", "–", ";", "(", "[",
                                    "«", "'", "|", "→", "•", "=", ">", "/", " -"))


PARTICLE = r"(?:al|el|ben|bin|ibn|abu|bou|d|l)[-'’]"
CAPW = r"(?:" + PARTICLE + r")?[A-ZÀ-ÖØ-Þ][^\W\d_]*(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*\.?(?![\w])"
CONNECT = r"(?:&|de|du|des|van|von|der|den|di|da|del|la|le|of)"
SEQ = re.compile(r"(?<![\w@/])" + CAPW + r"(?:(?:[ \t]+" + CONNECT + r")?[ \t]+"
                 + CAPW + r")*")
TOKEN = re.compile(CAPW + r"|" + CONNECT + r"(?=[ \t])")
TITLE_BEFORE = re.compile(r"\b(?:" + "|".join(sorted(TITLES, key=len, reverse=True))
                          + r")\.?[ \t]+$", re.I)


def domain_stems(text):
    """Company names hiding in email and web addresses: 'quillonlabs' from
    someone@quillonlabs.io. Free mail providers say nothing about anyone."""
    stems = set()
    for m in re.finditer(r"@([\w\-]+(?:\.[\w\-]+)+)|(?:https?://)?(?:www\.)([\w\-]+(?:\.[\w\-]+)+)"
                         r"|https?://([\w\-]+(?:\.[\w\-]+)+)", text):
        host = (m.group(1) or m.group(2) or m.group(3)).lower().split(".")
        stem = host[-2] if len(host) >= 2 else host[0]
        if len(stem) >= 3 and stem not in FREE_MAIL and stem not in PUBLIC:
            stems.add(stem)
    return stems


def _runs(text):
    """Runs of capitalised words, cut where a sentence ends inside one:
    "CTO. Filed" is two runs; "J. Okafor" and "Osterlund & Co." are one."""
    for m in SEQ.finditer(text):
        run = []
        for t in TOKEN.finditer(m.group(0)):
            w = t.group(0)
            # "Ottoline Vasquez of Brightwell Capital" is a person and a
            # company; "Bank of Montreal" is one name.
            if w == "of" and not (run and fold(run[-1][2]) in OF_HEADS):
                if run:
                    yield run
                run = []
                continue
            run.append((t.start() + m.start(), t.end() + m.start(), w))
            if w.endswith(".") and len(w) > 2 and fold(w[:-1]) not in TITLES \
                    and fold(w[:-1]) not in ORG_SUFFIX:
                yield run
                run = []
        if run:
            yield run


OF_HEADS = {"bank", "university", "institute", "college", "school", "museum",
            "department", "ministry", "council", "house", "board", "city",
            "state", "chamber", "society", "academy", "church", "hospital",
            "office", "court", "republic", "kingdom", "duke", "duchess"}

DETERMINERS = {"the", "this", "that", "such", "said", "each", "any", "our",
               "your", "le", "la", "les", "ce", "cette", "el", "los", "las"}

def _defined_term(after):
    """After "the" or "this", an ordinary capitalised word followed by a
    verb or punctuation is a contract's defined term ("This Agreement is",
    "the Company, effective"); followed by a noun it names something ("the
    Lantern deal", "the Kestrel deck")."""
    m = re.match(r"[ \t]+([a-zà-ÿ][\w'’\-]*)", after)
    return not m or fold(m.group(1)) in STOPWORDS


# Small words a title keeps lowercase between its capitalised ones. Not
# "and": "Rose and Hope" is two people, not a title.
TITLE_JOIN = r"(?:by|of|the|de|du|des|la|le)"


def _title_neighbour(side, before):
    """True when the capitalised word next door, across at most one small
    word, is itself an ordinary word: the two are a title. "Lunch with
    Rose" is not one: "Lunch" opens the sentence and "with" joins nothing."""
    if before:
        m = re.search(r"([A-Z][\w'’\-]*)[ \t]+(?:" + TITLE_JOIN + r"[ \t]+)?$", side)
        # A sentence's first word is capitalised for grammar, not a title.
        if m and _sentence_start(side, m.start(1)):
            return False
    else:
        m = re.match(r"[ \t]+(?:" + TITLE_JOIN + r"[ \t]+)?([A-Z][\w'’\-]*)", side)
    return bool(m) and is_ordinary(m.group(1))


def guess_names(text, keep=frozenset()):
    """Names nobody listed, from their shape. Returns [(surface, label,
    tokens)] where tokens are the distinctive words, so a later "Vasquez"
    alone hides with "Ottoline Vasquez".

    The rule: mid-sentence, a run of capitalised words is a name ("met
    Rose", "the Lantern deal", "Jasper Reinholt") unless every word in it
    is one that is capitalised for other reasons: a job or team word, a
    month, a famous name, a known acronym. At the start of a sentence
    capitals prove nothing, so the ordinary words she writes herself are
    trimmed off the front ("Thanks Bastien") and what is left must be a
    word she never writes, or a first name."""
    firsts = first_names()
    stems = domain_stems(text)
    found = []

    def public(t):
        f = re.sub(r"['’](?:ll|re|ve|d|m|t)$", "", fold(t.rstrip(".")))
        return (f in PUBLIC or f in keep or f in COMMON_ACRONYMS or f in CALENDAR
                or f in KIN or f in ROLE_WORDS or f in TITLES or len(f) <= 1)

    for toks in _runs(text):
        # A possessive or a full stop is not part of the name.
        toks = [(s, e - (2 if re.search(r"['’]s$", w) else 0) - (1 if w.endswith(".") and fold(w[:-1]) not in ORG_SUFFIX else 0),
                 re.sub(r"['’]s$", "", w).rstrip(".") if fold(w.rstrip(".")) not in ORG_SUFFIX else w)
                for s, e, w in toks]
        caps = [t for t in toks if re.match(r"(?:" + PARTICLE + r")?[A-ZÀ-ÖØ-Þ]", t[2]) or t[2] == "&"]
        if not caps:
            continue
        titled = bool(TITLE_BEFORE.search(text[max(0, caps[0][0] - 12):caps[0][0]]))
        while caps and fold(caps[0][2].rstrip(".")) in TITLES:
            caps, titled = caps[1:], True
        project = False
        if caps and fold(caps[0][2]) in PROJECT_CUES and len(caps) > 1:
            caps, project = caps[1:], True
        org = len(caps) > 1 and (fold(caps[-1][2].rstrip(".")) in ORG_SUFFIX
                                 or fold(caps[0][2]) in ORG_PREFIX)
        at_start = bool(caps) and _sentence_start(text, caps[0][0])
        # Sentence furniture off the front: "The", "Thanks", "Bonjour",
        # "Meeting" — words she writes in lowercase herself.
        if at_start and not (titled or project):
            # "Thanks Bastien", "Call Okafor", "Relancer Grace" lose their
            # first word; "Hunter Vance" and "TARRAGON SYSTEMS" do not: an
            # ordinary word followed by a name is the name's first half.
            first = True
            while caps and not (len(caps[0][2]) == 1 and len(caps) > 1) \
                    and fold(caps[0][2].rstrip(".")) not in TITLES and (
                    _opener(caps[0][2]) or caps[0][2] == "&"
                    or (public(caps[0][2]) and not org)
                    or (first and is_ordinary(caps[0][2]) and not org
                        and (len(caps) == 1 or is_ordinary(caps[1][2]) or public(caps[1][2])))) \
                    and not (org and fold(caps[0][2]) in ORG_PREFIX):
                # Only the sentence's first word is capitalised for grammar:
                # in "Relancer Grace", Grace is not an opener.
                caps, first = caps[1:], False
            # "Dear Dr Halvorsen": the title shows once the greeting is off.
            while caps and len(caps) > 1 and fold(caps[0][2].rstrip(".")) in TITLES:
                caps, titled = caps[1:], True
        while caps and fold(caps[0][2]) in STOPWORDS and len(caps) > 1:
            caps = caps[1:]
        # "Google Drive", "Microsoft Teams": a famous name and ordinary words.
        if any(fold(w) in PUBLIC for _, _, w in caps) and all(
                fold(w) in PUBLIC or is_ordinary(w) or public(w) for _, _, w in caps):
            continue
        while caps and (caps[-1][2] == "&" or (public(caps[-1][2]) and not (
                len(caps[-1][2]) == 1 and len(caps) > 1 and text[caps[-1][1]:caps[-1][1] + 1] == "."))):
            caps = caps[:-1]
        while caps and public(caps[0][2]) and not (len(caps[0][2]) == 1 and len(caps) > 1) \
                and not (org and fold(caps[0][2]) in ORG_PREFIX):
            caps = caps[1:]
        if not caps:
            continue
        words = [w for _, _, w in caps]
        named = [w for w in words if not public(w) and w != "&"
                 and fold(w.rstrip(".")) not in ORG_SUFFIX]
        if not named and not (titled or project):
            continue
        start, end = caps[0][0], caps[-1][1]
        still_start = _sentence_start(text, start)
        before = re.findall(r"[\w']+", text[max(0, start - 30):start].lower())
        cue = before[-1] if before else ""
        camel = any(re.search(r"[a-zà-ÿ][A-Z]", w) for w in named)
        stem_hit = fold("".join(words)) in stems or any(fold(w) in stems for w in words)
        acronym = len(words) == 1 and words[0].isupper()

        if acronym and not (titled or project or stem_hit):
            if len(re.sub(r"[^A-Z]", "", words[0])) < 3:
                continue
        elif still_start and not (titled or project or org or camel or stem_hit):
            # Capitals prove nothing here. A dictionary word alone is
            # listed, not hidden ("Rowan completely dismissed...").
            if len(words) == 1 and is_ordinary(words[0]) and fold(words[0]) not in firsts:
                continue
            if all(is_ordinary(w) for w in named):
                continue
        elif not (titled or project or org or camel or stem_hit) \
                and all(fold(w) in dictionary_proper() for w in named) \
                and cue not in COMPANY_CUES:
            continue            # Florida, Lincoln: listed, not hidden
        elif not (titled or project or org or camel or stem_hit) and len(words) > 1 \
                and all(is_ordinary(w) for w in named):
            continue            # "Managing Innovation": a title, listed
        elif not (titled or project or org or camel or stem_hit) and len(words) == 1 \
                and is_ordinary(words[0]) and (
                    re.match(r"[ \t]+\d", text[end:])            # "Session 3"
                    or _title_neighbour(text[:start], before=True)
                    or _title_neighbour(text[end:], before=False)):
            continue            # "Studio Course": a title, not a name
        elif not (titled or project or org or camel or stem_hit) and len(words) == 1 \
                and is_ordinary(words[0]) and cue in DETERMINERS \
                and _defined_term(text[end:]):
            continue            # "This Agreement is": a contract's defined term

        if titled:
            label = "Person"
        elif project:
            label = "Project"
        elif org or stem_hit:
            label = "Company"
        elif camel:
            label = "Product" if len(words) == 1 else "Name"
        elif acronym:
            label = "Name"
        elif cue in COMPANY_CUES and len(words) == 1:
            label = "Company"
        elif len([w for w in named if not w.isupper() and not is_ordinary(w)]) >= 2 \
                or fold(words[0]) in firsts:
            label = "Person"
        else:
            label = "Name"
        dist = [w for w in named if not w.isupper() and (
            (label == "Person" and len(w) >= 3) or (len(w) >= 4 and not is_ordinary(w)))]
        found.append((text[start:end], label, dist))
    return found


# ---- matching and masking ----------------------------------------------------

def _nk(s, keep_case=False):
    """The lookup key a match and its term share: no accents, a hyphen
    read as a space, and case folded unless the term is case-bound."""
    return (_strip(s) if keep_case else fold(s)).replace("-", " ")


def _word_too(surface):
    """A name that is also an ordinary word ("Rose", a company called
    "Wise"): both the dictionary and her own writing must agree, so a name
    she types in lowercase in file names stays a name."""
    import model
    f = fold(surface)
    return (f in common_words() and is_ordinary(surface)) \
        or f in model.AMBIGUOUS_NAMES or f in CALENDAR


def _term_regexes(terms):
    """Two alternations, longest first. A surface that is also an ordinary
    word ("Rose", a company called "Wise") only counts capitalised and
    mid-sentence; anything else matches in any case and with or without
    accents, so a name typed in lowercase in a chat still hides."""
    import model
    loose, strict = {}, {}
    for surface, key, label in terms:
        f = fold(surface)
        one_word_common = " " not in surface and _word_too(surface)
        (strict if one_word_common else loose).setdefault(
            _nk(surface, one_word_common), (key, label, surface))

    def build(d, flags):
        if not d:
            return None
        alts = sorted(d, key=len, reverse=True)
        return re.compile(r"(?<![\w@])(?<!\w-)(?:" + "|".join(_accent_rx(a) for a in alts)
                          + r")(?![\w@]|-\w)", flags)
    return (build(loose, re.I), loose), (build(strict, 0), strict)


def find_spans(text, terms, numbers=False, extra=()):
    """Every span to hide: (start, end, key, label). Overlaps go to the
    longest, so a full name beats the first name and an email beats both."""
    cands = []
    (rl, dl), (rs, ds) = _term_regexes(terms)
    if rl:
        for m in rl.finditer(text):
            key, label, _ = dl[_nk(m.group(0))]
            cands.append((m.start(), m.end(), key, label))
    if rs:
        for m in rs.finditer(text):
            key = ds[_nk(m.group(0), True)][0]
            # "Penny Vasseur" found in this text makes a later "Penny
            # mentioned..." her too; a contact's ordinary-word name opening
            # a sentence stays ambiguous.
            if _sentence_start(text, m.start()) and not key.startswith("guess:"):
                continue
            # A contact called May is still a month after "in" or before a day.
            if fold(m.group(0)) in CALENDAR and (
                    re.search(r"\b(?:in|on|by|until|till|since|before|after|early|"
                              r"late|mid|end|of|from|to|en|de|fin|debut)[ \t]+$",
                              fold(text[max(0, m.start() - 12):m.start()]))
                    or re.match(r"[ \t]+\d", text[m.end():])):
                continue
            key, label, _ = ds[_nk(m.group(0), True)]
            cands.append((m.start(), m.end(), key, label))
    pats = PATTERNS + ([NUMBERS] if numbers else [])
    for label, rx in pats:
        for m in rx.finditer(text):
            g = 1 if m.lastindex else 0         # a cue word stays, its value goes
            s = m.group(g)
            if label == "Phone":
                digits = re.sub(r"\D", "", s)
                if not 9 <= len(digits) <= 15 or DATE_LIKE.match(s.strip()):
                    continue
            if label in ("Link", "Address"):
                s = s.rstrip(".,;: ")
            cands.append((m.start(g), m.start(g) + len(s),
                          label.lower() + ":" + re.sub(r"\s", "", s).lower(), label))
    cands += list(extra)        # last, so an equal list or pattern span wins
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    spans, end = [], -1
    for c in cands:
        if c[0] >= end:
            spans.append(c)
            end = c[1]
    return spans


# ---- the local name model ---------------------------------------------------

ROOT = os.path.dirname(BRAIN)
NER_PYTHON = os.path.join(BRAIN, ".venv-ner", "bin", "python")
NER_WORKER = os.path.join(HERE, "anonymize_ner.py")
MODEL_LABELS = {"person": "Person", "organization": "Company", "company": "Company",
                "project name": "Project", "product": "Product",
                "street address": "Address", "username": "Handle"}


NO_NETWORK = "(version 1)(allow default)(deny network*)"


class ModelError(Exception):
    pass


def model_wanted():
    """On when it is installed, unless config says `"model": false`."""
    return os.path.exists(NER_PYTHON) and \
        (_cfg().get("anonymize") or {}).get("model", True) is not False


def model_spans(text):
    """Names the local model finds, offline, in its own Python. Raises
    ModelError rather than returning nothing: a silent failure would look
    exactly like a text with no names in it."""
    if not os.path.exists(NER_PYTHON):
        raise ModelError("not installed")
    models = os.path.join(BRAIN, ".models")
    env = dict(os.environ, HF_HOME=os.path.join(models, "hf"),
               XDG_CACHE_HOME=os.path.join(models, "cache"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1", TOKENIZERS_PARALLELISM="false")
    cands = _lower_unknowns(text)
    chars = list(text)
    for st, _ in cands:
        if len(chars[st].upper()) == 1:
            chars[st] = chars[st].upper()
    capped = "".join(chars)
    probes = []
    # Clause by clause: next to a capitalised name in the same clause the
    # model loses "Dax" ("Dear Dr Halvorsen, lol tell Dax hi"), alone it
    # scores 0.98.
    for m in re.finditer(r"[^\n.!?,;:]+[.!?,;:]*", text):
        if any(m.start() <= st < m.end() for st, _ in cands):
            probes.append([m.start(), capped[m.start():m.end()]])
    # The model runs with networking switched off by macOS itself, not only
    # by the offline flags: whatever it reads cannot leave the Mac through it.
    cmd = [NER_PYTHON, NER_WORKER]
    if shutil.which("sandbox-exec"):
        cmd = ["sandbox-exec", "-p", NO_NETWORK] + cmd
    try:
        r = subprocess.run(cmd, input=json.dumps({"text": text, "probes": probes}),
                           capture_output=True, text=True, timeout=180, env=env)
    except subprocess.TimeoutExpired:
        raise ModelError("timed out")
    if r.returncode:
        raise ModelError((r.stderr.strip().splitlines() or ["error"])[-1][:120])
    try:
        spans = json.loads(r.stdout)
    except ValueError:
        raise ModelError("unreadable answer")
    # From the capitalised copy, only a whole unknown word counts, and only
    # when the model is sure: names scored 0.92-0.99 there (dax, léa, jb,
    # saltbrook), foreign everyday words 0.77-0.83 (prestataire, gimnasio).
    cand = set(cands)
    return [dict(sp, text=text[sp["start"]:sp["end"]]) for sp in spans
            if not sp.get("probe")
            or ((sp["start"], sp["end"]) in cand and sp["score"] >= 0.9)]


def _lower_unknowns(text):
    """Lowercase words no dictionary or her own writing knows: where a chat
    hides a name ("tell dax", "léa a dit"). Slang is on the ordinary list."""
    out = []
    for m in re.finditer(r"(?<![\w@./\-])[a-zà-ÿ][a-zà-ÿ'’]{1,}(?![\w@/])", text):
        w = m.group(0)
        f = fold(w)
        if f in MODERN or f in FR_COMMON or f in ES_COMMON or f in STOPWORDS \
                or f in PUBLIC or f in COMMON_ACRONYMS or f in CALENDAR or f in KIN \
                or f in VERBS or is_plain(w) or is_ordinary(w):
            continue
        out.append((m.start(), m.end()))
    return out


def _trim_span(text, sp, keep):
    """The model's span without public words or titles at its ends: "Tante
    Odile" hides Odile, "14 rue des Mimosas, 75011 Paris" leaves Paris."""
    s, e = sp["start"], sp["end"]

    def edge_ok(w):
        f = fold(w.strip(".,"))
        return not (f in PUBLIC or f in TITLES or f in KIN or f in keep or f in CALENDAR
                    or f in ROLE_WORDS or f in STOPWORDS or f in FR_COMMON or f in ES_COMMON)
    while True:
        m = re.match(r"\s*([^\s,]+)[\s,]*", text[s:e])
        if not m or m.end() >= e - s or edge_ok(m.group(1)):
            break
        s += m.end()
    while True:
        m = re.search(r"[\s,]*([^\s,]+)\s*$", text[s:e])
        if not m or m.start() == 0 or edge_ok(m.group(1)):
            break
        e = s + m.start()
    if s >= e:
        return None
    return dict(sp, start=s, end=e, text=text[s:e])


def _model_keeps(sp, keep):
    """The model's weak or ordinary finds are dropped: it calls "team" an
    organisation and "hey" a person at low confidence. An ordinary word
    stays only when the model is sure ("hope is handling the invoices")."""
    surface, score = sp["text"], sp["score"]
    f = fold(surface)
    if len(f) < 2 or f in keep or f in STOPWORDS or f in MODERN or f in KIN \
            or f in ROLE_WORDS or f in PUBLIC or f in COMMON_ACRONYMS \
            or f in CALENDAR or f in TITLES or f in FR_COMMON or f in ES_COMMON:
        return False
    if " " not in surface and is_ordinary(surface):
        return score >= 0.7
    return score >= 0.5


def mask(text, also=(), keep=(), numbers=False, guess=True, use_model=None, found=None):
    """(masked text, key, info). The key maps each placeholder to what it
    hid; when one thing appears under several forms it restores the longest,
    so "[Person 1]" comes back as the full name. info has 'guessed' (the
    placeholders the brain did not know) and 'leaks' (should be empty)."""
    keep = _keep_set(keep)
    terms = known_terms(also, keep)
    guessed_keys = set()
    if guess:
        for stem in domain_stems(text):
            _term(terms, stem, "guess:" + stem, "Company", keep)
            guessed_keys.add("guess:" + stem)
        for surface, label, dist in guess_names(text, keep):
            key = "guess:" + fold(surface)
            joined = fold(re.sub(r"[\s&.\-]", "", surface))
            if any(t[1] == "guess:" + joined for t in terms):
                key = "guess:" + joined      # "Quillon Labs" is quillonlabs.io
            n = len(terms)
            _term(terms, surface, key, label, keep)
            for w in dist:
                _term(terms, w, key, label, keep)
            if len(terms) > n:
                guessed_keys.add(key)
    extra, model_state = [], "off"
    if found is not None:
        model_state = "on"          # read ahead by the caller (the test run)
    elif guess and (use_model if use_model is not None else model_wanted()):
        try:
            found = model_spans(text)
            model_state = "on"
        except ModelError as exc:
            found, model_state = [], f"failed ({exc})"
    if found:
        known = {fold(t[0]): t[1] for t in terms}
        for sp in found:
            label = MODEL_LABELS.get(sp["label"], "Name")
            sp = _trim_span(text, sp, keep)
            if not sp or not _model_keeps(sp, keep):
                continue
            surface = sp["text"]
            key = known.get(fold(surface)) or "guess:" + fold(surface)
            extra.append((sp["start"], sp["end"], key, label))
            if key.startswith("guess:"):
                guessed_keys.add(key)
                # Elsewhere in the text too, unless it is also an ordinary
                # word: "dax" hides everywhere, "hope" only where the model
                # saw a person.
                if not _word_too(surface):
                    n = len(terms)
                    _term(terms, surface, key, label, keep)
                    if len(terms) == n:
                        extra.pop()
    spans = find_spans(text, terms, numbers, extra)
    by_key, counts, mapping, out, pos = {}, Counter(), {}, [], 0
    for s, e, key, label in spans:
        if key not in by_key:
            counts[label] += 1
            by_key[key] = f"{label} {counts[label]}"
        ph = by_key[key]
        surface = text[s:e]
        if len(surface) > len(mapping.get(ph, "")):
            mapping[ph] = surface
        out.append(text[pos:s])
        out.append(f"[{ph}]")
        pos = e
    out.append(text[pos:])
    masked = "".join(out)
    info = {"guessed": [by_key[k] for k in by_key if k in guessed_keys],
            "leaks": leaks(masked, mapping), "model": model_state}
    return masked, mapping, info


def leaks(masked, mapping):
    """Anything hidden that still appears in the masked text, read again
    from scratch. Ordinary words are skipped: 'Rose' hidden as a name may
    rightly stay as a flower at the start of a sentence."""
    bare = re.sub(r"\[[^\]]*\]", " ", masked)
    out = []
    for ph, real in mapping.items():
        if " " not in real and _word_too(real):
            continue
        if re.search(r"(?<![\w@])" + _accent_rx(real) + r"(?![\w@])", bare, re.I):
            out.append(real)
    return out


def _ph_rx(placeholders):
    """Every way an AI rewrites a placeholder: "[Person 1]", "Person 1",
    "person 1", "PERSON 1", "Person1", "[Person-1]", but never "Person 12"."""
    alts = sorted(placeholders, key=len, reverse=True)
    body = "|".join(r"[\s_\-]*".join(map(re.escape, ph.split(" "))) for ph in alts)
    return re.compile(r"\[\s*(" + body + r")\s*\]|(?<![\w\[])(" + body + r")(?![\w\]])", re.I)


def _norm_ph(s):
    return re.sub(r"[\s_\-]+", "", s).lower()


def unmask(text, mapping):
    """Put the real words back, whichever way the AI wrote the placeholder."""
    if not mapping:
        return text
    by_norm = {_norm_ph(ph): real for ph, real in mapping.items()}
    rx = _ph_rx(mapping)
    return rx.sub(lambda m: by_norm.get(_norm_ph(m.group(1) or m.group(2)), m.group(0)), text)


STRAY = re.compile(r"\[\s*([A-Z][a-z]+(?: [a-z]+)? \d+)\s*\]")


def strays(text, mapping):
    """Bracketed placeholders the key does not know: the AI invented one,
    or this answer came from a different masking."""
    known = {_norm_ph(ph) for ph in mapping}
    return sorted({m.group(1) for m in STRAY.finditer(text)
                   if _norm_ph(m.group(1)) not in known})


def best_key(text):
    """The saved key this answer was made from: the one whose placeholders
    it uses most, then the one it has fewest unknown placeholders for, then
    the newest. "[Person 1]" is someone different in every masking, so the
    newest key alone would put the wrong name back after two maskings."""
    scored = []
    for i, k in enumerate(_load_keys()):
        if not k.get("map"):
            continue
        hits = len({_norm_ph(m.group(1) or m.group(2))
                    for m in _ph_rx(k["map"]).finditer(text)})
        if hits:
            scored.append(((hits, -len(strays(text, k["map"])), -i), k))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = dict(scored[0][1])
    # Two maskings fit equally well and would restore different names.
    best["unsure"] = len(scored) > 1 and scored[1][0][:2] == scored[0][0][:2] \
        and unmask(text, scored[1][1]["map"]) != unmask(text, best["map"])
    return best


def still_visible(masked, mapping, keep=()):
    """Capitalised words left in the masked text that are not ordinary
    words: names this tool could not place. Shown every run. An ordinary
    word counts too when it is capitalised mid-sentence ("met Rose"),
    because that is where an unknown name hides best."""
    common, keep = common_words(), _keep_set(keep)
    labels = {w.lower() for ph in mapping for w in ph.split() if not w.isdigit()}
    seen = []
    for m in re.finditer(r"(?<![\w\[])[A-ZÀ-Þ][\w'’\-]{2,}", masked):
        w = re.sub(r"['’]s$", "", m.group(0))
        low = fold(w)
        if re.sub(r"['’](?:ll|re|ve|d|m|t)$", "", low) in common or low in CALENDAR \
                or low in KIN or low in labels or low in PUBLIC \
                or low in COMMON_ACRONYMS or low in keep or low in TITLES or w in seen:
            continue
        if is_plain(w) and (w.isupper() or len(w) <= 3 or _sentence_start(masked, m.start())
                            or re.match(r"[ \t]+[A-Z\[]", masked[m.end():])
                            or re.search(r"[A-Z\]][\w.]*[ \t]+$", masked[max(0, m.start() - 30):m.start()])):
            continue        # a Title Case heading, not a hidden name
        seen.append(w)
    return seen


# ---- the key store ----------------------------------------------------------

def _load_keys():
    try:
        with open(KEYS, encoding="utf-8") as f:
            return json.load(f) or []
    except (OSError, ValueError):
        return []


def save_key(mapping, source=""):
    keys = _load_keys()
    kid = hashlib.sha1(json.dumps(mapping, sort_keys=True).encode()
                       + datetime.now().isoformat().encode()).hexdigest()[:6]
    keys.insert(0, {"id": kid, "made": datetime.now().isoformat(timespec="seconds"),
                    "source": source, "map": mapping})
    os.makedirs(os.path.dirname(KEYS), mode=0o700, exist_ok=True)
    tmp = KEYS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(keys[:KEEP_KEYS], f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, KEYS)
    return kid


def get_key(kid=None):
    keys = _load_keys()
    for k in keys:
        if kid is None or k["id"] == kid:
            return k
    return None


def remember(also=(), keep=()):
    """Save words into config's anonymize block, touching nothing else in a
    hand-formatted file."""
    path = os.path.join(BRAIN, "config.json")
    with open(path, encoding="utf-8") as f:
        s = f.read()
    m = re.search(r'\n  "anonymize": ', s)
    if not m:
        raise SystemExit("config.json has no anonymize block to remember into.")
    block, end = json.JSONDecoder().raw_decode(s, m.end())
    for field, words in (("terms", also), ("keep", keep)):
        cur = block.setdefault(field, [])
        have = {fold(str(x).partition("=")[0].strip()) for x in cur}
        cur.extend(w for w in words if fold(w.partition("=")[0].strip()) not in have)
    body = json.dumps(block, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    s = s[:m.end()] + body + s[end:]
    json.loads(s)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


# ---- input and output --------------------------------------------------------

def read_source(path=None, clip=False):
    if clip:
        return subprocess.run(["pbpaste"], capture_output=True, text=True,
                              check=True).stdout
    if not path or path == "-":
        return sys.stdin.read()
    import school
    if school.is_confidential(path):
        raise SystemExit("That file's name marks it confidential, so it is not "
                         "opened. Masking it would not lift the NDA.")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        r = subprocess.run(["pdftotext", "-layout", path, "-"],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("Could not read that PDF: " + r.stderr.strip())
        return r.stdout
    if ext in (".docx", ".doc", ".rtf", ".odt", ".html", ".pages"):
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("Could not read that file: " + r.stderr.strip())
        return r.stdout
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def write_out(text, clip=False, out=None):
    if clip:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
    elif out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def report(mapping, info, visible, loose=False):
    kinds = Counter(ph.rsplit(" ", 1)[0].lower() for ph in mapping)
    plural = {"person": "people", "company": "companies", "address": "addresses"}
    hid = ", ".join(f"{n} {plural.get(k, k + 's') if n > 1 else k}"
                    for k, n in kinds.most_common()) or "nothing"
    lines = [f"Hidden: {hid}."]
    if info.get("model", "off").startswith("failed"):
        lines.append("The local name model did not run, " + info["model"][7:]
                     + ": only plain code looked. Lowercase names may be visible.")
    if info["leaks"]:
        import agents
        lines.append("LEAK, still in the masked text: " + ", ".join(info["leaks"])
                     + ". Do not paste it; tell " + agents.short() + ".")
    if info["guessed"]:
        lines.append("Guessed, hidden though the brain doesn't know them: "
                     + ", ".join(f"{mapping[p]} [{p}]" for p in info["guessed"]))
        lines.append('  Keep any visible with --keep "Word".')
    if visible:
        lines.append(("Not hidden (--loose)" if loose else "Still visible")
                     + ", check none of these is a name: "
                     + ", ".join(visible[:40]) + (" …" if len(visible) > 40 else ""))
        lines.append('  Hide any of them with --also "Word, Other word".')
    return "\n".join(lines)


def _split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def model_spans_many(texts):
    """One model load for many texts: they are read joined, then the names
    handed back to the text each came from."""
    sep, joined, starts = "\n\n\n", "", []
    for t in texts:
        starts.append(len(joined))
        joined += t + sep
    per = [[] for _ in texts]
    for sp in model_spans(joined):
        i = max(j for j, st in enumerate(starts) if st <= sp["start"])
        if sp["end"] <= starts[i] + len(texts[i]):
            per[i].append(dict(sp, start=sp["start"] - starts[i], end=sp["end"] - starts[i]))
    return per


def run_tests(verbose=False, guess=True, path=CASES, use_model=None):
    """The test set: how much of what should go went, how much of what
    should stay stayed. 'Hard' cases are scored apart: they need a reader
    of meaning, not shapes."""
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    score = {False: [0, 0], True: [0, 0]}
    kept = [0, 0]
    misses, over, leaked = [], [], []
    on = guess and (use_model if use_model is not None else model_wanted())
    founds = model_spans_many([c["text"] for c in cases]) if on else [None] * len(cases)
    print("Layers: plain code" + (" + local name model" if on else " only"))
    for c, found in zip(cases, founds):
        masked, mapping, info = mask(c["text"], c.get("also", ()), (), False, guess,
                                     use_model=on, found=found)
        bare = fold(re.sub(r"\[[^\]]*\]", " ", masked))
        hard = bool(c.get("hard"))
        for h in c.get("hide", []):
            gone = not re.search(r"(?<![\w@])" + re.escape(fold(h)) + r"(?![\w])", bare)
            score[hard][0] += gone
            score[hard][1] += 1
            if not gone:
                misses.append((h, hard, masked))
        for k in c.get("keep", []):
            ok = fold(k) in bare
            kept[0] += ok
            kept[1] += 1
            if not ok:
                over.append((k, masked))
        leaked += info["leaks"]
    pct = lambda a, b: f"{a} of {b} ({round(100 * a / b) if b else 0}%)"
    print(f"Hidden, ordinary cases: {pct(*score[False])}")
    print(f"Hidden, hard cases:     {pct(*score[True])}")
    print(f"Kept visible as it should be: {pct(*kept)}")
    print("Leaks: " + (", ".join(leaked) if leaked else "none"))
    for h, hard, m in misses:
        print(f"  missed{' (hard)' if hard else ''}: {h}" + (f"\n      {m}" if verbose else ""))
    for k, m in over:
        print(f"  over-hid: {k}" + (f"\n      {m}" if verbose else ""))
    return 0 if not leaked else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("mask", "check", "ask"):
        p = sub.add_parser(name)
        if name == "ask":
            p.add_argument("question")
            p.add_argument("--file")
            p.add_argument("--yes", action="store_true", help="send without showing the masked text first")
        else:
            p.add_argument("file", nargs="?")
            p.add_argument("--clip", action="store_true", help="read (and for mask, write) the clipboard")
            p.add_argument("-o", "--out", help="write the masked text to this file")
        p.add_argument("--also", help="extra words to hide, comma separated")
        p.add_argument("--keep", help="words to leave visible, comma separated")
        p.add_argument("--remember", action="store_true", help="save --also and --keep for every run after")
        p.add_argument("--numbers", action="store_true", help="hide amounts and percentages too")
        p.add_argument("--loose", action="store_true", help="flag guessed names instead of hiding them")
        p.add_argument("--no-model", action="store_true", help="plain code only, skip the local name model")
    p = sub.add_parser("unmask")
    p.add_argument("file", nargs="?")
    p.add_argument("--clip", action="store_true")
    p.add_argument("--key", help="which key (default: the newest)")
    p.add_argument("-o", "--out")
    p = sub.add_parser("test")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--loose", action="store_true", help="score without the guessing layer")
    p.add_argument("--cases", default=CASES, help="another test set to score")
    p.add_argument("--no-model", action="store_true", help="score plain code only")
    a = ap.parse_args(argv)

    if a.cmd == "test":
        return run_tests(a.verbose, guess=not a.loose, path=a.cases,
                         use_model=False if a.no_model else None)

    if a.cmd == "unmask":
        text = read_source(a.file, a.clip)
        k = get_key(a.key) if a.key else best_key(text)
        if not k:
            raise SystemExit("No key " + (a.key or "matches this text") + ": nothing to put back.")
        write_out(unmask(text, k["map"]), a.clip, a.out)
        left = strays(text, k["map"])
        if k.get("unsure"):
            print("Careful: more than one recent masking fits this answer; the newest was "
                  "used. Check the names, or pass --key.", file=sys.stderr)
        print(f"Names put back with key {k['id']} ({k.get('source') or 'unnamed'}, "
              f"{k.get('made', '')[:16].replace('T', ' ')})."
              + (f" Not in that key, left as is: {', '.join(left)}." if left else ""),
              file=sys.stderr)
        return 0

    also, keep = _split(a.also), _split(a.keep)
    if a.remember and (also or keep):
        remember(also, keep)
        print("Remembered for every run: " + ", ".join(also + keep), file=sys.stderr)

    if a.cmd in ("mask", "check"):
        text = read_source(a.file, a.clip)
        masked, mapping, info = mask(text, also, keep, a.numbers, not a.loose,
                                     False if a.no_model else None)
        visible = still_visible(masked, mapping, keep)
        if a.cmd == "check":
            for ph, real in mapping.items():
                print(f"[{ph}]  {real}")
            print(report(mapping, info, visible, a.loose))
            return 1 if info["leaks"] else 0
        if info["leaks"]:
            print(report(mapping, info, visible, a.loose), file=sys.stderr)
            raise SystemExit("Nothing written.")
        kid = save_key(mapping, os.path.basename(a.file or "") or ("clipboard" if a.clip else "stdin"))
        write_out(masked, a.clip, a.out)
        print(report(mapping, info, visible, a.loose), file=sys.stderr)
        print(f"Key {kid} kept. Put the names back in the answer with: "
              f"anonymize.py unmask{' --clip' if a.clip else ' FILE'}", file=sys.stderr)
        return 0

    # ask: one shared key for the question and the file, so a name in both
    # gets one placeholder.
    text = a.question + ("\n\n---\n\n" + read_source(a.file) if a.file else "")
    masked, mapping, info = mask(text, also, keep, a.numbers, not a.loose,
                                 False if a.no_model else None)
    visible = still_visible(masked, mapping, keep)
    if info["leaks"]:
        print(report(mapping, info, visible, a.loose), file=sys.stderr)
        raise SystemExit("Not sent.")
    if not a.yes:
        print(masked, "\n", report(mapping, info, visible, a.loose), sep="", file=sys.stderr)
        if not sys.stdin.isatty():
            raise SystemExit("Not sent: run it in a terminal to confirm, or add --yes.")
        if input("\nSend this? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("Not sent.")
    import llm
    out = llm.complete("anon", masked, system=SYSTEM, timeout=180)
    save_key(mapping, "ask")
    print(unmask(out["text"], mapping))
    return 0


if __name__ == "__main__":
    sys.exit(main())
