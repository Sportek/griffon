"""Everything that depends on Facebook's markup, in one place.

Facebook's class names are generated and change every few weeks, so nothing here relies on
them. The anchors used instead:

- a post is a `role="article"` element that is not inside another one (comments are
  nested articles);
- its id comes from a permalink href (`/groups/<id-or-slug>/posts/<id>`,
  `/groups/<...>/permalink/<id>`, `story_fbid=`, `multi_permalinks=`) or, failing that,
  from a photo link's `set=pcb.<id>` / `set=gm.<id>`;
- its text is in `data-ad-preview="message"` / `data-ad-comet-preview="message"` (stable for
  years), else the longest `dir="auto"` block outside the header and the comments;
- the timestamp is the text or aria-label of the permalink anchor ("3 h", "Hier à 14:30",
  "October 12 at 3:15 PM"), or an `abbr[data-utime]`;
- listing photos are `<img>` from fbcdn inside photo links. Profile pictures are SVG
  `<image>` elements (or `t39.30808-1` URLs) and are never kept.

The browser side (FEED_ARTICLES_JS, SEE_MORE_JS) only collects the outer HTML of the
top-level articles; the parsing is plain Python so it can be tested against saved HTML
(tests/fixtures/facebook/). The poster's name and profile link are never extracted.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlsplit

from selectolax.parser import HTMLParser, Node

from ..normalize import _MONTHS, _fold

BASE = "https://www.facebook.com"

# --- groups -----------------------------------------------------------------------

_GROUP_URL_RE = re.compile(r"facebook\.com/groups/([^/?#\s]+)", re.I)
_GROUP_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def group_key(value: str) -> str:
    """'https://www.facebook.com/groups/logementpmr.annonces/' -> 'logementpmr.annonces';
    a bare id or slug ('242242325809377', 'groups/123/') is accepted too."""
    value = value.strip()
    if m := _GROUP_URL_RE.search(value):
        key = m.group(1)
    else:
        key = value.strip("/")
        if key.lower().startswith("groups/"):
            key = key[len("groups/"):]
        key = key.split("/")[0]
    key = unquote(key).strip()
    if not key or not _GROUP_KEY_RE.match(key):
        raise ValueError(f"not a Facebook group URL or id: {value!r}")
    return key


def parse_groups(value: str | None) -> list[str]:
    """FACEBOOK_GROUPS: comma/whitespace-separated URLs or ids -> unique group keys, in order."""
    keys: list[str] = []
    for part in re.split(r"[,\s]+", value or ""):
        if part.strip() and (key := group_key(part)) not in keys:
            keys.append(key)
    return keys


def feed_url(key: str) -> str:
    """Group feed, newest posts first (Facebook ignores the parameter when it can't sort)."""
    return f"{BASE}/groups/{key}/?sorting_setting=CHRONOLOGICAL"


def post_url(key: str, post_id: str) -> str:
    return f"{BASE}/groups/{key}/posts/{post_id}/"


# --- permalinks -------------------------------------------------------------------

_PERMALINK_RE = re.compile(r"/groups/([^/?#]+)/(?:posts|permalink)/([A-Za-z0-9]+)")
_PHOTO_SET_RE = re.compile(r"(?:^|[?&])set=(?:pcb|gm)\.(\d+)")


def parse_permalink(href: str | None) -> tuple[str | None, str | None]:
    """Returns (group key, post id) from a post link, or (None, None)."""
    if not href:
        return None, None
    href = unquote(href)
    if m := _PERMALINK_RE.search(href):
        return m.group(1), m.group(2)
    parts = urlsplit(href)
    query = parse_qs(parts.query)
    for name in ("story_fbid", "multi_permalinks"):
        if query.get(name):
            g = re.search(r"/groups/([^/?#]+)", parts.path)
            return (g.group(1) if g else None), query[name][0].split(",")[0]
    return None, None


# --- timestamps -------------------------------------------------------------------

_REL_RE = re.compile(
    r"^(?:il y a\s+)?(\d+)\s*(s|sec|secs|secondes?|seconds?|m|min|mins|minutes?|mn|h|hr|hrs|heures?|hours?"
    r"|j|jours?|d|days?|sem|semaines?|w|wk|wks|weeks?|mois|mo|months?|an|ans|y|yr|yrs|years?)\b"
)
_UNIT_SECONDS = {
    "s": 1, "m": 60, "h": 3600, "j": 86400, "d": 86400, "w": 7 * 86400, "mo": 30 * 86400, "y": 365 * 86400,
}
_TIME_RE = re.compile(r"(\d{1,2})\s*[:h]\s*(\d{2})?\s*(am|pm)?")
_DAY_MONTH_RE = re.compile(r"(\d{1,2})(?:er)?\s+([a-z]+)\.?(?:\s+(\d{4}))?")
_MONTH_DAY_RE = re.compile(r"([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?")
_MONTH_ABBR = {k[:3]: v for k, v in _MONTHS.items()} | {"juil": 7, "sept": 9, "janv": 1, "fevr": 2}


def _unit(word: str) -> str:
    if word in ("mo", "mois") or word.startswith("month"):
        return "mo"
    if word.startswith(("sem", "w")):
        return "w"
    if word.startswith(("an", "y")):
        return "y"
    if word.startswith(("j", "d")):
        return "j"
    if word.startswith(("h",)):
        return "h"
    if word.startswith(("s",)):
        return "s"
    return "m"


def _month(word: str) -> int | None:
    word = word.rstrip(".")
    return _MONTHS.get(word) or _MONTH_ABBR.get(word) or _MONTH_ABBR.get(word[:4]) or _MONTH_ABBR.get(word[:3])


def _clock(text: str) -> tuple[int, int] | None:
    if not (m := _TIME_RE.search(text)):
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and hour < 12:
        hour += 12
    if m.group(3) == "am" and hour == 12:
        hour = 0
    return (hour, minute) if hour < 24 and minute < 60 else None


def parse_timestamp(text: str | None, now: datetime | None = None) -> str | None:
    """Facebook's post time label -> ISO 8601 (UTC). Relative labels ('3 h', '2 j', '5 min',
    'Hier à 14:30', 'Yesterday at 2:30 PM') are resolved against `now`; absolute ones
    ('12 octobre', 'October 12 at 3:15 PM', '3 mars 2025') too. None when unrecognized."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    folded = re.sub(r"\s+", " ", _fold(text)).strip(" ·.")
    if folded in ("a l'instant", "just now", "maintenant", "now"):
        return now.isoformat(timespec="seconds")
    if m := _REL_RE.match(folded):
        seconds = int(m.group(1)) * _UNIT_SECONDS[_unit(m.group(2))]
        return (now - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    clock = _clock(folded)
    if folded.startswith(("hier", "yesterday")):
        day = (now - timedelta(days=1)).date()
    else:
        day = None
        for regex, order in ((_DAY_MONTH_RE, "dm"), (_MONTH_DAY_RE, "md")):
            for m in regex.finditer(folded):
                d, mo = (m.group(1), m.group(2)) if order == "dm" else (m.group(2), m.group(1))
                month = _month(mo)
                if not month:
                    continue
                year = int(m.group(3)) if m.group(3) else now.year
                try:
                    day = datetime(year, month, int(d)).date()
                except ValueError:
                    continue
                if not m.group(3) and day > now.date():
                    day = day.replace(year=year - 1)  # "12 décembre" read in January
                break
            if day:
                break
    if not day:
        return None
    hour, minute = clock or (12, 0)
    # Labels are in the account's local time; Montreal is UTC-4/-5, close enough at this scale.
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone(timedelta(hours=-5)))
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


# --- posts ------------------------------------------------------------------------

SEE_MORE_LABELS = {"see more", "voir plus", "en voir plus", "afficher la suite", "afficher plus"}


@dataclass
class Post:
    post_id: str
    group: str | None
    url: str | None
    text: str
    published_at: str | None = None
    time_label: str | None = None
    photos: list[str] = field(default_factory=list)


def _in_nested_article(node: Node, root: Node) -> bool:
    parent = node.parent
    while parent is not None and parent is not root and parent.mem_id != root.mem_id:
        if parent.attributes.get("role") == "article":
            return True
        parent = parent.parent
    return False


def _in_header(node: Node, root: Node) -> bool:
    parent = node
    while parent is not None and parent.mem_id != root.mem_id:
        if parent.tag in ("h2", "h3", "h4", "strong") or parent.attributes.get("role") == "button":
            return True
        parent = parent.parent
    return False


def _own(root: Node, selector: str) -> list[Node]:
    """Matches of `selector` inside `root` but not inside a nested (comment) article."""
    return [n for n in root.css(selector) if not _in_nested_article(n, root)]


def _text_of(node: Node) -> str:
    for button in node.css('[role="button"]'):
        if _fold(button.text(strip=True)) in SEE_MORE_LABELS:
            button.decompose()
    # Facebook draws emoji as <img alt="🏠" src=".../emoji.php/...">.
    for img in node.css("img"):
        if "emoji" in (img.attributes.get("src") or "") and img.attributes.get("alt"):
            img.replace_with(img.attributes["alt"])
    # Line breaks only at block boundaries: inline links/hashtags stay in their sentence.
    for block in node.css("div, p, li"):
        block.insert_after("\n")
    for br in node.css("br"):
        br.replace_with("\n")
    text = node.text(separator="")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _post_text(article: Node) -> str:
    for selector in ('[data-ad-preview="message"]', '[data-ad-comet-preview="message"]',
                     '[data-ad-rendering-role="story_message"]'):
        if found := _own(article, selector):
            return _text_of(found[0])
    blocks = [n for n in _own(article, 'div[dir="auto"], span[dir="auto"]') if not _in_header(n, article)]
    texts = [_text_of(n) for n in blocks]
    return max(texts, key=len, default="")


def _is_listing_photo(src: str) -> bool:
    return (
        src.startswith("https://")
        and ("fbcdn.net" in src or "scontent" in src)
        and "t39.30808-1/" not in src  # profile pictures
        and "/rsrc.php" not in src
        and "emoji" not in src
    )


def _post_photos(article: Node) -> list[str]:
    photos: list[str] = []
    for img in _own(article, "img"):
        src = img.attributes.get("src") or ""
        anchor = img.parent
        while anchor is not None and anchor.tag != "a" and anchor.mem_id != article.mem_id:
            anchor = anchor.parent
        href = (anchor.attributes.get("href") or "") if anchor is not None and anchor.tag == "a" else ""
        in_photo_link = any(k in href for k in ("/photo", "photo.php", "/photos/"))
        if in_photo_link and _is_listing_photo(src) and src not in photos:
            photos.append(src)
    return photos


def _post_root(tree: HTMLParser) -> Node | None:
    """The post itself: a feed unit ([aria-posinset], Facebook's current markup, where only the
    comments are role="article"), else a top-level article (older markup)."""
    return tree.css_first("[aria-posinset]") or tree.css_first('[role="article"]') or tree.body


def parse_article(html: str, *, group: str | None = None, now: datetime | None = None) -> Post | None:
    """One feed post's outer HTML -> Post, or None when it has no recognizable id or text.

    The post id comes from the post's own permalink, else from its photo set (set=pcb.<id>),
    else from the links of its comments (/posts/<id>/?comment_id=...), which point at the post.
    The current markup only fills the timestamp link on hover, hence the fallbacks."""
    tree = HTMLParser(html)
    article = _post_root(tree)
    if article is None:
        return None

    post_id = post_group = time_label = published = None
    for a in _own(article, "a[href]"):
        g, pid = parse_permalink(a.attributes.get("href"))
        if pid:
            post_id, post_group = pid, g
            label = (a.attributes.get("aria-label") or a.text(strip=True) or "").strip()
            if label:
                time_label = label
                published = parse_timestamp(label, now)
            break
    if post_id is None:
        for a in _own(article, "a[href]"):
            if m := _PHOTO_SET_RE.search(urlsplit(unquote(a.attributes.get("href") or "")).query):
                post_id = m.group(1)
                break
    if post_id is None:
        for a in article.css("a[href]"):  # comments included: their links name the post
            href = a.attributes.get("href") or ""
            if "comment_id=" in href and (found := parse_permalink(href))[1]:
                post_group, post_id = found
                break
    if published is None and (abbr := next(iter(_own(article, "abbr[data-utime]")), None)):
        try:
            utime = int(abbr.attributes.get("data-utime") or "")
            published = datetime.fromtimestamp(utime, timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass

    # Photos first: _post_text strips "See more" buttons and line breaks from the tree.
    photos = _post_photos(article)
    text = _post_text(article)
    if not post_id or not text:
        return None
    group = post_group or group
    return Post(
        post_id=post_id,
        group=group,
        url=post_url(group, post_id) if group else None,
        text=text,
        published_at=published,
        time_label=time_label,
        photos=photos,
    )


def split_articles(page_html: str) -> list[str]:
    """Python twin of FEED_ARTICLES_JS: outer HTML of the posts of a saved page, i.e. the feed
    units ([aria-posinset]) when there are any, else the top-level articles (older markup)."""
    tree = HTMLParser(page_html)
    scope = tree.css_first('[role="feed"]') or tree.root
    units = scope.css("[aria-posinset]")
    if units:
        return [u.html for u in units if u.css_first("a[href]") is not None]
    out = []
    for node in scope.css('[role="article"]'):
        parent, nested = node.parent, False
        while parent is not None:
            if parent.attributes.get("role") == "article":
                nested = True
                break
            parent = parent.parent
        if not nested:
            out.append(node.html)
    return out


# --- browser side -----------------------------------------------------------------

# Outer HTML of the feed's top-level posts (comments are nested articles).
# Posts of the feed: [aria-posinset] units (current markup, comments are the only role="article"),
# else top-level articles (older markup). Python twin: split_articles.
FEED_ARTICLES_JS = """() => {
  const scope = document.querySelector('[role="feed"]') || document;
  const units = [...scope.querySelectorAll('[aria-posinset]')];
  // Loading placeholders have no link yet.
  if (units.length) return units.filter(u => u.querySelector('a[href]')).map(u => u.outerHTML);
  return [...scope.querySelectorAll('[role="article"]')]
    .filter(a => !a.parentElement || !a.parentElement.closest('[role="article"]'))
    .map(a => a.outerHTML);
}"""

# Marks the "See more" buttons of top-level posts so Playwright can click them one by one.
SEE_MORE_JS = """(labels) => {
  const scope = document.querySelector('[role="feed"]') || document;
  let n = 0;
  const units = scope.querySelector('[aria-posinset]') !== null;
  const posts = units ? '[aria-posinset] [role="button"]' : '[role="article"] [role="button"]';
  for (const b of scope.querySelectorAll(posts)) {
    const article = b.closest('[role="article"]');
    // A comment's button: inside an article that is not the post itself.
    const comment = units ? (article !== null && article !== b.closest('[aria-posinset]'))
                          : (article.parentElement && article.parentElement.closest('[role="article"]'));
    if (comment) continue;
    if (b.dataset.griffonSeen) continue;
    if (labels.includes((b.innerText || '').trim().toLowerCase())) {
      b.dataset.griffonSeen = '1';
      b.dataset.griffonMore = '1';
      n++;
    }
  }
  return n;
}"""

SEE_MORE_SELECTOR = '[data-griffon-more="1"]'
