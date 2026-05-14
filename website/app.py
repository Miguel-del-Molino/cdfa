from flask import Flask, request
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, DCTERMS, FOAF, SKOS , DC 
import os

app = Flask(__name__)

# === CONFIG ===
SCHEMA_NS = "https://iaaa.es/cdfa/"
FUEROS_FILE = "data/fueros_complete.ttl"
CONCEPTS_FILE = "results/subjects.ttl"
THESAURUS_FILE = "data/tesauro-de-derecho-foral-aragones.rdf"

MAX_LITERAL_CHARS = 150

# ✅ TRANSLATION DICTIONARY
TRANSLATIONS = {
    'es': {
        'title': '📚 CDFA: Fueros de Reino de Aragón',
        'triples': 'triples',
        'concepts': 'conceptos',
        'home': '🏠 Inicio',
        'properties': 'Propiedades',
        'related_resources': 'Recursos Relacionados',
        'resource': 'Recurso',
        'not_found': 'Recurso no encontrado',
        'no_exist': "Este recurso no existe en el dataset CDFA.",
        'book_info': '📖 INFO LIBRO',
        'title_es': 'TÍTULO (ES)',
        'title_la': 'TÍTULO (LA)',
        'subject': '🏷️ dct:subject',
        'haspart': 'hasPart'
    },
    'en': {
        'title': '📚 CDFA: Charters of the Aragon Kingdom',
        'triples': 'triples',
        'concepts': 'concepts',
        'home': '🏠 Home',
        'properties': 'Properties',
        'related_resources': 'Related Resources',
        'resource': 'Resource',
        'not_found': 'Resource Not Found',
        'no_exist': "This resource doesn't exist in the CDFA dataset.",
        'book_info': '📖 BOOK INFO',
        'title_es': 'TITLE (ES)',
        'title_la': 'TITLE (LA)',
        'subject': '🏷️ dct:subject',
        'haspart': 'hasPart'
    }
}

HIERARCHY_LABELS = {
    'es': ["Libro", "Parte", "Capítulo", "Sección", "Frase", "Cortes Generales", "Persona", "Ubicación", "Concepto", "Cuadro de clasificación"],
    'en': ["Book", "Part", "Chapter", "Section", "Phrase", "CourtEvent", "Person", "Location", "Concept", "ConceptSchema"]
}

# Load RDF graphs
#print("Loading RDF graphs...")
g = Graph()
g.parse(FUEROS_FILE, format="turtle")

concepts_g = Graph()
if os.path.exists(CONCEPTS_FILE):
    concepts_g.parse(CONCEPTS_FILE, format="turtle")
    #print(f"Loaded {len(concepts_g)} concept triples")

thesaurus_g = Graph()
if os.path.exists(THESAURUS_FILE):
    thesaurus_g.parse(THESAURUS_FILE)
    #print(f"Loaded {len(thesaurus_g)} thesaurus triples")

# ✅ EXTRACT ConceptScheme URL from thesaurus file
CONCEPT_SCHEME_URL = None
for s, p, o in thesaurus_g.triples((None, RDF.type, SKOS.ConceptScheme)):
    CONCEPT_SCHEME_URL = str(s)
    #print(f"✅ Found ConceptScheme: {CONCEPT_SCHEME_URL}")
    break

if not CONCEPT_SCHEME_URL:
    CONCEPT_SCHEME_URL = "https://ibersid.eu/tesauros/tesauro_00/vocab/"
    #print(f"⚠️  No ConceptScheme found, using fallback: {CONCEPT_SCHEME_URL}")

# Bind namespaces
cdfa = Namespace(SCHEMA_NS)
g.bind("cdfa", cdfa)
g.bind("dct", DCTERMS)
g.bind("foaf", FOAF)
g.bind("rdfs", RDFS)
g.bind("skos", SKOS)

concepts_g.bind("dct", DCTERMS)
thesaurus_g.bind("skos", SKOS)

HIERARCHY = ["Book", "Part", "Chapter", "Section", "Phrase", "CourtEvent", "Person", "Location", "Concept", "ConceptScheme"]
ENDPOINT_TERMINALS = {"Location", "Person", "CourtEvent", "Concept"}

def get_lang():
    """Get language from query param, default to Spanish"""
    lang = request.args.get('lang', 'es').lower()
    return 'es' if lang == 'es' else 'en'

def t(key):
    """Translation helper"""
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)


def short_literal(text: str) -> str:
    # Show FULL text on phrase pages, truncated elsewhere
    frag = request.view_args.get('frag', '') if request.view_args else ''
    if 'phrase' in frag.lower():
        return  text.replace('\\n', '<br>').replace('  ', '&nbsp;&nbsp;')
    if len(text) <= MAX_LITERAL_CHARS:
        return text
    return text[:MAX_LITERAL_CHARS] + "..."

def get_concept_label(concept_uri: str) -> str:
    uri = URIRef(concept_uri)
    for _, _, label in thesaurus_g.triples((uri, SKOS.prefLabel, None)):
        if isinstance(label, Literal) and label.language == "es":
            return str(label)
    for _, _, label in thesaurus_g.triples((uri, SKOS.prefLabel, None)):
        return str(label)
    # ✅ AltLabel fallback
    for _, _, label in thesaurus_g.triples((uri, SKOS.altLabel, None)):
        if isinstance(label, Literal) and label.language == "es":
            return str(label)
    # ✅ Fragment as final fallback
    return str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]

def get_concept_link(concept_uri: str, as_internal=False) -> tuple:
    uri = URIRef(concept_uri)
    label = get_concept_label(concept_uri)

    # 1. skos:exactMatch (external canonical URL)
    matches = list(thesaurus_g.triples((uri, SKOS.exactMatch, None)))
    if matches and not as_internal:
        match_url = matches[0][2]
        if isinstance(match_url, URIRef):
            return label, str(match_url)

    # 2. skos:related (alternative external URL)
    related = list(thesaurus_g.triples((uri, SKOS.related, None)))
    if related and not as_internal:
        rel_url = related[0][2]
        if isinstance(rel_url, URIRef):
            return label, str(rel_url)

    # 3. Concept's own URI
    if list(thesaurus_g.triples((uri, RDF.type, SKOS.Concept))):
        frag = get_frag(uri)
        if as_internal:
            return label, f"/cdfa/resource/{frag}"
        return label, str(uri)

    # 4. skos:seeAlso links
    for _, _, seealso in thesaurus_g.triples((uri, SKOS.seeAlso, None)):
        if isinstance(seealso, URIRef):
            if not as_internal:
                return label, str(seealso)
            frag = get_frag(seealso)
            return label, f"/cdfa/resource/{frag}"

    # 5. fallback: scheme + fragment
    frag = str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    fallback = f"{CONCEPT_SCHEME_URL.rstrip('/')}/{frag}"
    if as_internal:
        return label, f"/cdfa/resource/{frag}"
    return label, fallback



def get_resource_titles(uri: URIRef) -> tuple:
    query_es = f"""PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?title
    WHERE {{ <{uri}> dct:title ?title . FILTER(lang(?title) = "es") }}
    LIMIT 1"""
    query_la = f"""PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?title
    WHERE {{ <{uri}> dct:title ?title . FILTER(lang(?title) = "la") }}
    LIMIT 1"""
    results_es = g.query(query_es)
    results_la = g.query(query_la)
    title_es = str(list(results_es)[0].title) if results_es else ""
    title_la = str(list(results_la)[0].title) if results_la else ""
    return title_es, title_la

def get_resource_title(uri: URIRef) -> str:
    title_es, _ = get_resource_titles(uri)
    return title_es or str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]

def get_display_label(uri: URIRef, frag: str = "") -> tuple:
    frag_name = frag or str(uri).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
    
    if 'book' in frag_name.lower():
        try:
            info = get_book_info(uri)
            return info['title'] or frag_name, 'book'
        except:
            return frag_name, 'book'
    elif 'location' in frag_name.lower():
        try:
            return get_location_name(uri), 'location'
        except:
            return frag_name, 'location'
    elif 'person' in frag_name.lower():
        try:
            return get_person_name(uri), 'person'
        except:
            return frag_name, 'person'
    elif 'courtevent' in frag_name.lower():
        try:
            title, date = get_courtevent_info(uri)
            return f"{title}" if date else title or frag_name, 'courtevent'
        except:
            return frag_name, 'courtevent'
    elif 'section' in frag_name.lower():
        try:
            info = get_section_info(uri)
            return info['title'] or frag_name, 'section'
        except:
            return frag_name, 'section'
    else:
        return get_resource_title(uri), 'generic'

def get_book_info(book_uri: URIRef):
    query = f"""PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?title ?description ?created
    WHERE {{ <{book_uri}> dct:title ?title .
        OPTIONAL {{ <{book_uri}> dct:description ?description FILTER(lang(?description) = "es") }}
        OPTIONAL {{ <{book_uri}> dct:created ?created }}
        FILTER(lang(?title) = "es") }}"""
    results = g.query(query)
    if results:
        row = list(results)[0]
        return {
            'title': str(row.title),
            'description': str(row.description) if row.description else "",
            'created': str(row.created) if row.created else ""
        }
    return {'title': '', 'description': '', 'created': ''}

def get_section_info(section_uri):
    query = f"""PREFIX dct: <http://purl.org/dc/terms/>
    PREFIX cdfa: <{SCHEMA_NS}>
    SELECT ?title ?chrono ?systematic
    WHERE {{ <{section_uri}> dct:title ?title FILTER(lang(?title) = "es") .
        OPTIONAL {{ <{section_uri}> cdfa:chronologicalVersionPage ?chrono }}
        OPTIONAL {{ <{section_uri}> cdfa:systematicVersionPage ?systematic }} }}"""
    results = g.query(query)
    if results:
        row = list(results)[0]
        return {
            'title': str(row.title),
            'chrono': str(row.chrono) if row.chrono else "",
            'systematic': str(row.systematic) if row.systematic else ""
        }
    return {'title': '', 'chrono': '', 'systematic': ''}

def get_location_name(location_uri: URIRef) -> str:
    query = f"""PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?name
    WHERE {{ <{location_uri}> foaf:name ?name . FILTER(lang(?name) = "es") }}
    LIMIT 1"""
    results = g.query(query)
    if results:
        return str(list(results)[0].name)
    return get_resource_title(location_uri)

def get_person_name(person_uri: URIRef) -> str:
    query = f"""PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?name
    WHERE {{ <{person_uri}> foaf:name ?name . FILTER(lang(?name) = "es") }}
    LIMIT 1"""
    results = g.query(query)
    if results:
        return str(list(results)[0].name)
    return get_resource_title(person_uri)

def get_courtevent_info(courtevent_uri):
    query = f"""PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?title ?date
    WHERE {{ <{courtevent_uri}> dct:title ?title .
        OPTIONAL {{ <{courtevent_uri}> dct:date ?date }}
        FILTER(lang(?title) = "es") }}
    LIMIT 1"""
    results = g.query(query)
    if results:
        row = list(results)[0]
        title = str(row.title)
        date = str(row.date) if row.date else ""
        return title, date
    return "", ""

def get_section_phrases(section_uri):
    query = f"""PREFIX cdfa: <{SCHEMA_NS}>
    PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?phrase ?desc_es ?desc_la ?phrase_id
    WHERE {{ <{section_uri}> dct:hasPart ?phrase .
        ?phrase a cdfa:Phrase .
        OPTIONAL {{ ?phrase dct:description ?desc_es FILTER(lang(?desc_es) = "es") }}
        OPTIONAL {{ ?phrase dct:description ?desc_la FILTER(lang(?desc_la) = "la") }}
        BIND(STRAFTER(STR(?phrase), "phrase-") AS ?phrase_id) }}
    ORDER BY ?phrase_id"""
    results = g.query(query)
    return list(results)

def get_section_concepts(section_uri):
    # Look in both graphs
    in_g = list(g.triples((section_uri, DCTERMS.subject, None)))
    in_concepts = list(concepts_g.triples((section_uri, DCTERMS.subject, None)))
    # Aggregate all distinct ?concept objects
    concepts = set()
    for s, p, o in in_g + in_concepts:
        if isinstance(o, URIRef):
            concepts.add(str(o))
    return list(concepts)


def get_frag(uri): 
    frag = str(uri).rsplit("/",1)[-1].rsplit("#",1)[-1]
    return frag.replace("skos/", "").strip('/')

def get_property_name(p):
    """✅ EXACT RDF NAMES: dc:title, skos:hasTopConcept, rdf:type, etc."""
    if p == RDF.type: return "rdf:type"
    if p == SKOS.prefLabel: return "skos:prefLabel"
    if p == SKOS.narrower: return "skos:narrower"
    if p == SKOS.broader: return "skos:broader"
    #if p == SKOS.inScheme: return "skos:inScheme"
    if p == SKOS.hasTopConcept: return "skos:hasTopConcept"
    if p == DCTERMS.title: return "dcterms:title"
    if p == DCTERMS.creator: return "dcterms:creator"
    if p == DCTERMS.description: return "dcterms:description"
    if p == DCTERMS.modified: return "dcterms:modified"
    if p == DC.title: return "dc:title"
    if p == DC.creator: return "dc:creator"
    if p == DC.rights: return "dc:rights"
    if p == DC.subject: return "dc:subject"
    if p == DC.language: return "dc:language"
    if p == DC.date: return "dc:date"
    return str(p).split('#')[-1] if '#' in str(p) else str(p).rsplit('/',1)[-1]

def try_both_uris(frag):
    uris_to_try = [
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/skos/{frag}"),      # ✅ Uses CONCEPT_SCHEME_URL
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/{frag}"),           
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/vocab/{frag}"),     
        URIRef(f"{SCHEMA_NS}{frag}")                                 # ✅ CDFA fallback
    ]
    for uri in uris_to_try:
        if list(thesaurus_g.triples((uri, None, None))) or list(g.triples((uri, None, None))):
            #print(f"✅ FOUND {frag} at: {uri}")
            return uri
    #print(f"❌ NOT FOUND {frag}")
    return None

def get_narrower(uri): return list(thesaurus_g.triples((uri, SKOS.narrower, None)))


def get_top_concepts(): 
    if not CONCEPT_SCHEME_URL: return []
    return list(thesaurus_g.triples((URIRef(CONCEPT_SCHEME_URL), SKOS.hasTopConcept, None)))
    
    
# === HOME ===
@app.route("/cdfa/")
@app.route("/cdfa")
def index():
    lang = get_lang()
    type_counts = {}
    for s, p, o in g.triples((None, RDF.type, None)):
        type_label = str(o).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        type_counts[type_label] = type_counts.get(type_label, 0) + 1
    
    concept_count = len(list(thesaurus_g.triples((None, RDF.type, SKOS.Concept))))
    type_counts["Concept"] = concept_count

    html = f"""<!DOCTYPE html>
<html><head><title>{t('title')}</title>
<style>
    body {{ font-family: 'Segoe UI', Arial; max-width: 1600px; margin: 0 auto; padding: 30px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }}
    .header {{ text-align: center; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }}
    h1 {{ color: #2c3e50; font-size: 3em; margin: 0; }}
    .lang-switch {{ position: absolute; top: 20px; right: 20px; z-index: 1000; }}
    .lang-btn {{ background: #3498db; color: white; padding: 10px 20px; margin: 0 5px; border-radius: 25px; text-decoration: none; font-weight: 500; transition: all 0.3s; }}
    .lang-btn.active {{ background: #2ecc71; }}
    .lang-btn:hover {{ transform: scale(1.05); }}
    .hierarchy {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 25px; margin: 40px 0; }}
    .hierarchy-item {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px; border-radius: 15px; text-align: center; color: white; box-shadow: 0 10px 30px rgba(0,0,0,0.2); transition: all 0.3s; }}
    .hierarchy-item:hover {{ transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.3); }}
</style></head>
<body>
    <div class="lang-switch">
        <a href="/cdfa/?lang=es" class="lang-btn {'active' if lang == 'es' else ''}">🇪🇸 ES</a>
        <a href="/cdfa/?lang=en" class="lang-btn {'active' if lang == 'en' else ''}">🇬🇧 EN</a>
    </div>
    <div class="header">
        <h1>{t('title')}</h1>
        <p style="color: #7f8c8d; font-size: 1.3em;"><strong>{len(g):,} {t('triples')}</strong> | <strong>{concept_count:,} {t('concepts')}</strong></p>
    </div>
    
    <div class="hierarchy">
"""
    icons = {"Book": "📖", "Part": "📄", "Chapter": "📑", "Section": "📝", "Phrase": "✍️", "CourtEvent": "⚖️", "Person": "👤", "Location": "📍", "Concept": "🏷️"}
    hierarchy_labels = HIERARCHY_LABELS[lang]
    for i, type_name in enumerate(HIERARCHY):
        # skip "ConceptScheme" so it won't appear as a type tile
        if type_name == "ConceptScheme":
            continue
        count = type_counts.get(type_name, 0)
        icon = icons.get(type_name, "🔗")
        label = hierarchy_labels[i]
        html += f'<div class="hierarchy-item"><a href="/cdfa/type/{type_name.lower()}?lang={lang}"><div style="font-size: 3.5em;">{icon}</div><div>{label}</div><div style="font-size: 2em;">{count}</div></a></div>'

    # ✅ Add ConceptScheme button
    label = HIERARCHY_LABELS[lang][9]
    if CONCEPT_SCHEME_URL:
        scheme_count = len(list(thesaurus_g.triples((None, RDF.type, SKOS.ConceptScheme))))
        html += f'''
        <div class="hierarchy-item">
            <a href="/cdfa/conceptscheme?lang={lang}">
                <div style="font-size: 3.5em;">🏛️</div>
                <div>{label}</div>
                <div style="font-size: 2em;">{scheme_count}</div>
            </a>
        </div>
        '''
    
    html += '</div></body></html>'
    return html

# === TYPE LIST ===
@app.route("/cdfa/type/<type_name>")
def by_type(type_name):
    lang = get_lang()
    class_map = {
        "book": cdfa.Book, "part": cdfa.Part, "chapter": cdfa.Chapter, 
        "section": cdfa.Section, "phrase": cdfa.Phrase, 
        "courtevent": cdfa.CourtEvent, "person": FOAF.Person, 
        "location": DCTERMS.Location
    }
    
    instances = []
    if type_name.lower() == "concept":
        for s, p, o in thesaurus_g.triples((None, RDF.type, SKOS.Concept)):
            instances.append(s)
    else:
        class_uri = class_map.get(type_name.lower())
        if class_uri:
            for s, p, o in g.triples((None, RDF.type, class_uri)):
                instances.append(s)
    
    html = f"""<!DOCTYPE html><html><head><title>{type_name.title()}</title>
<style>
body{{font-family:'Segoe UI',Arial;max-width:1400px;margin:0 auto;padding:50px;background:#f8f9fa}}
.lang-switch{{position:fixed;top:20px;right:20px;z-index:1000}}
ul{{column-count:3;list-style:none;padding:0}}
li{{background:white;margin:12px;padding:20px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);break-inside:avoid;display:flex;align-items:center}}
.concept-link{{color:#27ae60 !important;font-weight:600;text-decoration:none;display:block;padding:10px;border-radius:8px;background:linear-gradient(135deg,#e8f8f5,#d5f4e6);border-left:4px solid #2ecc71;transition:all 0.3s}}
.concept-link:hover{{background:linear-gradient(135deg,#d5f4e6,#b8f0d9);transform:translateX(5px);box-shadow:0 6px 20px rgba(46,204,113,0.3)}}
.resource-link{{color:#3498db;font-weight:600;text-decoration:none;display:block}}
.terminal-link{{color:#95a5a6;font-style:italic;font-weight:400;text-decoration:none;display:block;padding:10px;border-radius:8px;background:#ecf0f1;border-left:4px solid #bdc3c7}}
</style>
<body>
<div class="lang-switch">
    <a href="/cdfa/type/{type_name}?lang=es" class="lang-btn {'active' if lang == 'es' else ''}">🇪🇸 ES</a>
    <a href="/cdfa/type/{type_name}?lang=en" class="lang-btn {'active' if lang == 'en' else ''}">🇬🇧 EN</a>
</div>
<h1 style="text-align:center;color:#2c3e50">{type_name.title()}s ({len(instances)})</h1><ul>"""
    
    # CourtEvent sorting
    if type_name.lower() == "courtevent":
        def get_event_year(uri):
            query = f"""PREFIX dct: <http://purl.org/dc/terms/>
            SELECT ?date
            WHERE {{ <{uri}> dct:date ?date }}
            LIMIT 1"""
            result = g.query(query)
            if result:
                date_str = str(list(result)[0].date)
                return date_str[:4] if date_str else "9999"
            return "9999"
        sorted_instances = sorted(set(instances), key=get_event_year)
    else:
        sorted_instances = sorted(set(instances), key=lambda x: get_concept_label(str(x)) if type_name.lower() == "concept" else str(x))
    
    for s in sorted_instances[:3000]:
        short_name = str(s).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
        
        if type_name.lower() == "concept":
            label, internal_url = get_concept_link(str(s), as_internal=True)
            html += f'<li><a href="{internal_url}" class="concept-link">{label}</a></li>'
        elif short_name in ENDPOINT_TERMINALS:
            label, _ = get_display_label(s, short_name)
            html += f'<li><span class="terminal-link">🔸 {label}</span></li>'
        else:
            label, _ = get_display_label(s, short_name)
            html += f'<li><a href="/cdfa/resource/{short_name}?lang={lang}" class="resource-link">📋 {label}</a></li>'
    
    html += f'</ul><p style="text-align:center"><a href="/cdfa/?lang={lang}" style="background:#3498db;color:white;padding:18px 36px;border-radius:12px;font-size:1.3em;text-decoration:none;">{t("home")}</a></p></body></html>'
    return html

# === RESOURCE VIEW ===
@app.route("/cdfa/resource/<path:frag>")
def resource(frag):
    lang = get_lang()
    frag = frag.strip('/')
    
    # ✅ TRY CDFA FIRST, then Thesaurus URIs
    uri_candidates = [
        URIRef(f"{SCHEMA_NS}{frag}"),                          # 1. CDFA: https://iaaa.es/cdfa/510
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/skos/{frag}"),   # 2. Thesaurus: .../skos/510
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/{frag}"),        # 3. .../510
        URIRef(f"{CONCEPT_SCHEME_URL.rstrip('/')}/vocab/{frag}")   # 4. .../vocab/510
    ]
    
    uri = None
    for candidate in uri_candidates:
        # ✅ Check if EITHER graph has triples about this URI
        if (list(g.triples((candidate, None, None))) or 
            list(thesaurus_g.triples((candidate, None, None))) or
            list(g.query(f"CONSTRUCT WHERE {{ ?s ?p <{candidate}> . }}")) or
            list(thesaurus_g.query(f"CONSTRUCT WHERE {{ ?s ?p <{candidate}> . }}"))):
            uri = candidate
            #print(f"✅ FOUND {frag} → {uri}")
            break
    
    if not uri:
        return f"""<!DOCTYPE html><html><head><title>{t('not_found')}</title>
<style>body{{font-family:'Segoe UI',Arial;max-width:800px;margin:0 auto;padding:100px;background:#f8f9fa;text-align:center}}
.error-box{{background:white;padding:60px;border-radius:20px;box-shadow:0 15px 35px rgba(0,0,0,0.1)}}
h1{{color:#e74c3c;font-size:4em;margin:0}}
p{{color:#7f8c8d;font-size:1.3em;line-height:1.6}}</style>
<body><div class="error-box">
<h1>❌ {frag}</h1>
<p>{t('no_exist')}</p>
<a href="/cdfa/?lang={lang}" style="background:#3498db;color:white;padding:15px 30px;border-radius:12px;font-size:1.2em;text-decoration:none;display:inline-block;margin-top:30px">{t('home')}</a>
</div></body></html>""", 404
    
    # ✅ ALL FORWARD TRIPLES FROM BOTH GRAPHS
    triples = (list(g.triples((uri, None, None))) + 
               list(thesaurus_g.triples((uri, None, None))))
    
    # ✅ ALL INVERSE TRIPLES FROM BOTH GRAPHS
    inverse_query = f"CONSTRUCT WHERE {{ ?s ?p <{uri}> . }}"
    inverse_triples = (list(g.query(inverse_query)) + 
                       list(thesaurus_g.query(inverse_query)))
    
    return render_html_resource(uri, triples, inverse_triples, frag, lang)



@app.route("/cdfa/conceptscheme")
def conceptscheme():
    lang = get_lang()
    SKIP_CONCEPTSCHEME_PROPERTIES = {
        DC.creator,
        DC.contributor,        # dc:contributor
        DC.publisher,          # dc:publisher
        DC.rights,
        DC.subject,
        DC.description,        # dc:description
        DC.date,
        DCTERMS.modified,
        DC.language,
    }

    html = f"""<!DOCTYPE html><html><head><title>{t('title')} - ConceptScheme</title>
<style>
body{{font-family:'Segoe UI',Arial;max-width:1400px;margin:0 auto;padding:50px;background:#f8f9fa}}
.lang-switch{{position:fixed;top:20px;right:20px;z-index:1000}}
.lang-btn{{background:#3498db;color:white;padding:10px 20px;margin:0 5px;border-radius:25px;text-decoration:none;font-weight:500}}
.lang-btn.active{{background:#2ecc71}}
.scheme-box{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:50px;border-radius:25px;margin:50px 0;box-shadow:0 20px 40px rgba(0,0,0,0.1)}}
table{{width:100%;font-size:14px;overflow:hidden;background:white;border-radius:15px}}
th{{background:#2c3e50;color:white;padding:18px 15px;font-weight:600}}
td{{color:black;padding:18px 15px;border-bottom:1px solid #eee;vertical-align:top}}
.property-name{{font-weight:600;width:280px;font-family:monospace}}
.concept-link{{color:#27ae60;font-weight:500;padding:8px 14px;border-radius:8px;background:#e8f8f5;border-left:4px solid #2ecc71;display:inline-block;text-decoration:none}}
</style></head>
<body>
<div class="lang-switch">
    <a href="/cdfa/conceptscheme?lang=es" class="lang-btn {'active' if lang == "es" else ''}">🇪🇸</a>
    <a href="/cdfa/conceptscheme?lang=en" class="lang-btn {'active' if lang == "en" else ''}">🇬🇧</a>
</div>
<h1 style="text-align:center;color:#2c3e50;margin-bottom:40px">🏛️ ConceptScheme</h1>
<div class="scheme-box">
    <h2 style="color:white;margin-bottom:25px">📋 {t('properties')}</h2>
    <table><tr><th>Propiedad</th><th>Valor</th></tr>"""
    
    for s, p, o in thesaurus_g.triples((URIRef(CONCEPT_SCHEME_URL), None, None)):
        if p in SKIP_CONCEPTSCHEME_PROPERTIES:
            continue

        prop_name = get_property_name(p)

        # ✅ Special case: rdf:type → no link, just plain text
        if p == RDF.type and isinstance(o, URIRef):
            # show eg. "skos:ConceptScheme" or "ConceptScheme" as plain text
            obj_label = get_concept_label(str(o))
            html += f'<tr><td class="property-name">{prop_name}</td><td>{obj_label}</td></tr>'

        elif isinstance(o, URIRef):
            frag = get_frag(o)
            label = get_concept_label(str(o))
            html += f'<tr><td class="property-name">{prop_name}</td><td><a href="/cdfa/resource/{frag}" class="concept-link">{label}</a></td></tr>'

        else:
            html += f'<tr><td class="property-name">{prop_name}</td><td>{short_literal(str(o))}</td></tr>'
    
    html += f'''</table></div>
<p style="text-align:center">
    <a href="/cdfa/?lang={lang}" style="background:#3498db;color:white;padding:18px 36px;border-radius:12px;font-size:1.3em;text-decoration:none;">{t("home")}</a>
</p></body></html>'''
    return html
    
    
    
    
def render_html_resource(uri, triples, inverse_triples, frag, lang):
    label, rtype = get_display_label(uri, frag)

    SKIP_PROPERTIES = {
        RDF.type,
        DC.title,
        DC.creator,
        DCTERMS.publisher,
        DC.rights,
        DC.subject,
        DC.language,
        DC.date,
        DCTERMS.modified,
        SKOS.inScheme,
        SKOS.hasTopConcept,
    } 

    html = f"""<!DOCTYPE html><html><head><title>{label}</title>
<style>
body{{font-family:'Segoe UI',Arial;max-width:1400px;margin:0 auto;padding:30px;background:#f8f9fa}}
.lang-switch{{position:fixed;top:20px;right:20px;z-index:1000}}
.header{{background:white;padding:30px;border-radius:15px;box-shadow:0 8px 25px rgba(0,0,0,0.1);margin-bottom:30px;margin-top:60px}}
h1{{color:#2c3e50;font-size:2em}}
table{{width:100%;background:white;border-radius:12px;box-shadow:0 5px 20px rgba(0,0,0,0.1);font-size:14px}}
th{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:18px;font-weight:600}}
td{{padding:15px;border-bottom:1px solid #eee}}
a.resource-link{{color:#3498db;font-weight:500;text-decoration:none;display:block;padding:8px 0;border-left:3px solid #3498db;margin:2px 0}}
a.resource-link:hover{{background:#ebf3fd;color:#2980b9}}
a.concept-link{{color:#27ae60 !important;border-left-color:#2ecc71 !important;text-decoration:none;display:block;padding:8px 0}}
a.concept-link:hover{{background:#e8f8f5;color:#229954}}
a.terminal-link{{color:#95a5a6 !important;font-style:italic;border-left-color:#bdc3c7 !important}}
.literal-trunc{{color:#7f8c8d;background:#f8f9fa;padding:12px;border-radius:6px;cursor:help;white-space:pre-line !important;line-height:1.6 !important;word-wrap:break-word !important;display:block !important}}
.phrase-link a {{color:#e67e22 !important; border-left-color:#f39c12 !important; font-style:italic; font-weight:normal; display:inline !important; padding:0 !important; margin:0 !important; border-left:0 !important}}
.phrase-link a:hover {{background:transparent !important; color:#d68910 !important}}
</style></head>
<body>
<div class="lang-switch">
    <a href="/cdfa/resource/{frag}?lang=es" class="lang-btn {'active' if lang == 'es' else ''}">🇪🇸 ES</a>
    <a href="/cdfa/resource/{frag}?lang=en" class="lang-btn {'active' if lang == 'en' else ''}">🇬🇧 EN</a>
</div>
<div class="header">
    <h1>🔗 {label}</h1>
    <p style="color:#7f8c8d">{uri}</p>
    <a href="/cdfa/?lang={lang}" style="background:#3498db;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;margin-right:10px">{t('home')}</a>
</div>
"""

    all_properties = []

    try:
        title_es, title_la = get_resource_titles(uri)
        if title_es:
            all_properties.append(('TITLE (ES)', None, DCTERMS.title, Literal(title_es)))
        if title_la:
            all_properties.append(('TITLE (LA)', None, DCTERMS.title, Literal(title_la)))
    except:
        pass

    if 'book' in rtype.lower():
        try:
            book_info = get_book_info(uri)
            all_properties.append(
                ('📖 BOOK INFO', None, None,
                 Literal(f"Created: {book_info['created']} | Desc: {short_literal(book_info['description'])}"))
            )
        except:
            pass

    try:
        concepts = get_section_concepts(uri)
        for c in concepts[:100]:
            label, external_url = get_concept_link(c, as_internal=True)
            all_properties.append(
                ('🏷️ dct:subject', None, DCTERMS.subject, URIRef(c), label, external_url)
            )
    except:
        pass

    try:
        phrase_results = get_section_phrases(uri)
        seen_hasparts = set()
        for row in phrase_results[:100]:
            phrase_uri = row.phrase
            seen_hasparts.add(str(phrase_uri))
            desc_es = str(row.desc_es) if row.desc_es else ""
            desc_la = str(row.desc_la) if row.desc_la else ""
            phrase_id = str(row.phrase_id)
            phrase_text = short_literal(desc_es or desc_la or phrase_id)
            all_properties.append(
                ('hasPart', None, DCTERMS.hasPart, phrase_uri, phrase_text)
            )
    except:
        pass

    for s, p, o in triples:
        if p in SKIP_PROPERTIES:
            continue        
        if p == DCTERMS.title:
            continue
        if p == DCTERMS.hasPart and str(o) in seen_hasparts:
            continue
        if p == SKOS.inScheme:
            continue
            
            
        pred = str(p).split('#')[-1] if '#' in str(p) else str(p).rsplit('/', 1)[-1]
        if isinstance(o, URIRef):
            all_properties.append((pred, s, p, o))
        elif isinstance(o, Literal):
            all_properties.append((pred, s, p, o))

    # NEW: sections that use SKOS concepts as dct:subject
    is_skos_concept = (
        list(thesaurus_g.triples((uri, RDF.type, SKOS.Concept))) or
        list(thesaurus_g.triples((uri, SKOS.prefLabel, None)))
    )
    sections_as_subject = []

    if is_skos_concept:
        # Collect all sections that have this concept as dct:subject
        for s, p, o in g.triples((None, DCTERMS.subject, uri)):
            if "section" in str(s).lower():
                sections_as_subject.append(s)
        for s, p, o in concepts_g.triples((None, DCTERMS.subject, uri)):
            if "section" in str(s).lower():
                sections_as_subject.append(s)
        sections_as_subject = list(set(sections_as_subject))

        for section_uri in sorted(sections_as_subject, key=str):
            frag = get_frag(section_uri)
            label, _ = get_display_label(section_uri, frag)
            all_properties.append(
                ('🏷️ used as subject in section', None, DCTERMS.subject, section_uri, label)
            )
    # -----------

    html += f"<h2>📋 {t('properties')} ({len(triples)})</h2><table><tr><th>Predicate</th><th>Object</th></tr>"

    for prop in all_properties:
        if len(prop) == 6:  # CONCEPT
            pred_label, s, p, target_uri, display_text, external_url = prop
            obj_html = f'<a href="{external_url}" class="concept-link" title="{str(target_uri)}">{display_text}</a>'
            html += f'<tr><td style="font-weight:600">{pred_label}</td><td>{obj_html}</td></tr>'

        elif len(prop) == 5:  # Phrase or section-as-subject
            pred_label, s, p, target_uri, display_text = prop
            short_name = str(target_uri).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
            obj_html = f'<span class="phrase-link"><a href="/cdfa/resource/{short_name}?lang={lang}" title="{str(target_uri)}">{display_text}</a></span>'
            html += f'<tr><td style="font-weight:600">{pred_label}</td><td>{obj_html}</td></tr>'

        # -----------
        # NEW CASE: sections that use this concept as dct:subject
        # -----------
        elif len(prop) == 5 and prop[0] == '🏷️ used as subject in section':
            pred_label, s, p, target_uri, display_text = prop
            short_name = str(target_uri).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
            obj_html = f'<a href="/cdfa/resource/{short_name}?lang={lang}" class="resource-link" title="{str(target_uri)}">{display_text}</a>'
            html += f'<tr><td style="font-weight:600">{pred_label}</td><td>{obj_html}</td></tr>'
        # -----------

        else:  # Normal triples
            pred_label, s, p, o = prop

            if isinstance(o, URIRef):
                short_name = str(o).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
                if short_name in ENDPOINT_TERMINALS:
                    label, _ = get_display_label(o, short_name)
                    obj_html = f'<span class="terminal-link" title="{str(o)}">🔸 {label}</span>'
                elif list(thesaurus_g.triples((o, SKOS.prefLabel, None))):
                    # ✅ Internal link for SKOS concept
                    label, external_url = get_concept_link(str(o), as_internal=True)
                    obj_html = f'<a href="{external_url}" class="concept-link" title="{str(o)}">{label}</a>'
                else:
                    label, _ = get_display_label(o, short_name)
                    obj_html = f'<a href="/cdfa/resource/{short_name}?lang={lang}" class="resource-link" title="{str(o)}">{label}</a>'
            elif isinstance(o, Literal):
                display = short_literal(str(o))
                safe_full = str(o).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                title_attr = '' if 'phrase' in frag.lower() else f'title="{safe_full}"'
                obj_html = f'<span {title_attr} class="literal-trunc">{display}</span>'
                #obj_html = f'<span title="{safe_full}" class="literal-trunc">{display}</span>'
            else:
                obj_html = str(o)

            html += f'<tr><td style="font-weight:600">{pred_label}</td><td>{obj_html}</td></tr>'

    html += '</table>'
    
    # FIXED: Sort inverse triples by CourtEvent year
    is_skos_concept = (
        list(thesaurus_g.triples((uri, RDF.type, SKOS.Concept))) or
        list(thesaurus_g.triples((uri, SKOS.prefLabel, None)))
    )
    if not is_skos_concept:
        def sort_courtevent_year(triple):
            s, p, o = triple
            if "courtevent" in str(s).lower():
                date_props = [DCTERMS.date, DCTERMS.created, DC.date]
                for prop in date_props:
                    query = f"""SELECT ?date WHERE {{ <{s}> <{prop}> ?date }} LIMIT 1"""
                    result = g.query(query)
                    if result:
                        date_str = str(list(result)[0].date)
                        return date_str[:4] if len(date_str) >= 4 else "9999"
            return "9999"  # Non-CourtEvents or no date go to end
        
        sorted_inverse_triples = sorted(inverse_triples, key=sort_courtevent_year)
        
        html += f"<h2>🔗 {t('related_resources')} ({len(sorted_inverse_triples)})</h2><table><tr><th>{t('resource')}</th><th>Relation</th></tr>"
        for s, p, o in sorted_inverse_triples:
            s_frag = str(s).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
            if s_frag in ENDPOINT_TERMINALS:
                s_label, _ = get_display_label(s, s_frag)
                html += f"<tr><td><span class='terminal-link'>{s_label}</span></td><td><strong>{str(p).split('#')[-1] if '#' in str(p) else str(p).rsplit('/', 1)[-1]}</strong></td></tr>"
            else:
                s_label, _ = get_display_label(s, s_frag)
                pred = str(p).split('#')[-1] if '#' in str(p) else str(p).rsplit('/', 1)[-1]
                html += f"<tr><td><a href='/cdfa/resource/{s_frag}?lang={lang}' class='resource-link'>{s_label}</a></td><td><strong>{pred}</strong></td></tr>"
        html += "</table>"

    html += "</body></html>"

    return html




if __name__ == "__main__":
    #print("✅ CDFA FUEROS: ENGLISH/SPANISH TRANSLATION ✅ SYNTAX FIXED!")
    #print("✅ ?lang=en or ?lang=es - Language switcher top-right")
    #print("✅ No more syntax errors - COMPLETE working code")
    #print("https://127.0.0.1:5013/cdfa/")
    app.run(host="0.0.0.0", port=5013, debug=True)
