"""Pure, side-effect-free helpers to turn raw collected content into the
stable, hashable plain text used for deduplication and storage.

These functions never touch the Odoo ORM so they stay trivially unit
testable and reusable by future connectors (RSS, Légifrance, ...).

FR : Fonctions utilitaires pures, sans effet de bord, pour transformer le
contenu brut collecté en texte simple stable et hachable, utilisé pour la
déduplication et le stockage.

Ces fonctions ne touchent jamais l'ORM Odoo, ce qui les garde
trivialement testables unitairement et réutilisables par de futurs
connecteurs (RSS, Légifrance, ...).
"""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - bs4 is a documented dependency
    BeautifulSoup = None

_WHITESPACE_RE = re.compile(r"\s+")


def decode_bytes(raw_content, encoding_hint=None):
    """Decode raw bytes to text, tolerating unknown/wrong encodings.

    FR : Décode des octets bruts en texte, en tolérant les encodages
    inconnus/incorrects.
    """
    if isinstance(raw_content, str):
        return raw_content
    if raw_content is None:
        return ""
    for encoding in filter(None, [encoding_hint, "utf-8", "latin-1"]):
        try:
            return raw_content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_content.decode("utf-8", errors="replace")


def html_to_text(html_content):
    """Strip tags/scripts/styles from HTML and return readable plain text.

    FR : Retire les balises/scripts/styles du HTML et retourne un texte
    simple lisible.
    """
    if not html_content:
        return ""
    if BeautifulSoup is None:
        raise RuntimeError(
            "beautifulsoup4 is required to normalize HTML content."
        )
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return normalize_whitespace(text)


def normalize_whitespace(text):
    """Unicode-normalize and collapse whitespace into single spaces.

    FR : Normalise l'Unicode et réduit les espaces multiples à un seul
    espace.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def compute_content_hash(plain_text):
    """Stable SHA-256 (hex) of the normalized text used for deduplication.

    FR : SHA-256 stable (hexadécimal) du texte normalisé, utilisé pour la
    déduplication.
    """
    normalized = normalize_whitespace(plain_text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_pdf_text(raw_bytes):
    """Best-effort text extraction from a PDF. Returns None (instead of
    raising) when no PDF library is available or extraction fails, so the
    caller can flag the document for human review instead of crashing.

    FR : Extraction de texte best-effort depuis un PDF. Retourne None
    (plutôt que de lever une exception) quand aucune bibliothèque PDF
    n'est disponible ou que l'extraction échoue, afin que l'appelant
    puisse marquer le document pour revue humaine plutôt que de planter.
    """
    import io

    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return normalize_whitespace(" ".join(pages_text))
    except Exception:  # noqa: BLE001 - any parsing failure degrades gracefully
        return None


def normalize_canonical_url(url):
    """Return a stable canonical form of a URL: lowercase scheme/host, no
    fragment, sorted query string, no trailing slash on bare paths.

    FR : Retourne une forme canonique stable d'une URL : schéma/hôte en
    minuscules, sans fragment, chaîne de requête triée, sans slash final
    sur les chemins nus.
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))
