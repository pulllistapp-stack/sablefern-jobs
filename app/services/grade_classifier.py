"""eBay listing title → grade tier classifier.

Feeds the Multi-Grade price chart (ROADMAP #9). Every eBay listing we
snapshot passes through here to get bucketed into a canonical grade tag
so `card_price_snapshots.grade` carries something comparable across
sources.

Vocabulary (matches `CardPriceSnapshot.grade`):
    raw      — ungraded / no grade mentioned
    psa10    — PSA 10 Gem Mint
    psa9     — PSA 9 Mint
    psa8     — PSA 8 NM-Mint
    cgc10    — CGC 10 Pristine / Gem Mint
    cgc9.5   — CGC 9.5 Mint+
    cgc9     — CGC 9 Mint
    bgs10    — BGS 10 Pristine / Black Label
    bgs9.5   — BGS 9.5 Gem Mint
    bgs9     — BGS 9 Mint
    other    — grade mentioned but not in the canonical tier list
               (PSA 7, ACE, SGC, GMA, ISA, etc.)

Design notes:
* Case-insensitive.
* Grade token must sit next to the grader abbreviation (within ~5 chars)
  to avoid false hits on card titles like "Zacian V PSA 10 GEM MINT"
  vs "Zacian V-Union Set of 4" where PSA / 10 appear unrelated.
* Titles claiming multiple graders ("PSA 10 CGC 9.5 pair") — the first
  hit wins, since eBay listings are almost always a single graded slab.
* Purely numeric mentions like "grade 10" without a grader → 'other'.
"""

from __future__ import annotations

import re


GRADE_CANONICAL = {
    "raw",
    "psa10", "psa9", "psa8",
    "cgc10", "cgc9.5", "cgc9",
    "bgs10", "bgs9.5", "bgs9",
    # BGS Black Label / Pristine 10 — the "all four sub-grades hit 10"
    # tier. Distinct SKU from a regular BGS 10 (Black Label slabs are
    # framed in black and command 2-10× the price on chase cards).
    "bgs10bl",
    # TAG Grading — newer service (2024+) hot with chase collectors.
    # TAG 10 = Pristine, 9.5 = Gem Mint, 9 = Mint+.
    "tag10", "tag9.5", "tag9",
    "other",
}


# Compact spelling covers "PSA10", "PSA 10", "PSA-10", "P.S.A. 10".
# Number is captured so we can bucket it.
_PSA_RE = re.compile(
    r"\bP\.?\s*S\.?\s*A\.?\s*[-:# ]?\s*(\d{1,2}(?:\.\d)?)\b",
    re.IGNORECASE,
)
_CGC_RE = re.compile(
    r"\bC\.?\s*G\.?\s*C\.?\s*[-:# ]?\s*(\d{1,2}(?:\.\d)?)\b",
    re.IGNORECASE,
)
# CGC Pristine 10 — CGC's premium perfect-10 designation. Actually
# rarer than a regular CGC 10 and can command a 30-50% premium, but
# for our tile-level bucketing we treat it as cgc10 (buyers looking
# at "CGC 10 median" want to see clearing prices for the top tier).
# Same for the rarely-used "CGC PERFECT 10".
_CGC_PRISTINE_RE = re.compile(
    r"\bC\.?\s*G\.?\s*C\.?\s*(?:GEM\s*MINT\s*)?(?:PRISTINE|PERFECT)\s*10\b",
    re.IGNORECASE,
)
_BGS_RE = re.compile(
    r"\bB\.?\s*G\.?\s*S\.?\s*[-:# ]?\s*(\d{1,2}(?:\.\d)?)\b",
    re.IGNORECASE,
)
# Beckett is BGS's parent company; a meaningful fraction of eBay
# sellers list slabs as "Beckett 10" instead of "BGS 10" (or use
# both). The scraper runs a fallback Beckett-variant query for BGS
# tiers when the BGS pass returns too few, and this regex bucket
# those titles correctly. Same numeric grade schema as BGS.
_BECKETT_RE = re.compile(
    r"\bBECKETT\b\s*(?:GRADING(?:\s*SERVICES)?)?\s*[-:# ]?\s*"
    r"(\d{1,2}(?:\.\d)?)\b",
    re.IGNORECASE,
)
# BGS Black Label / Pristine 10 signals — all four subgrades == 10
# means Beckett stamps the slab with a black label. Different physical
# slab, meaningfully different market price (2-10× a regular BGS 10 on
# chase). Presence of any of these keywords in a BGS 10 listing routes
# it to the `bgs10bl` bucket instead of `bgs10`.
#
# Deliberately excluding bare "BL" and bare "Black" — both false-
# positive on unrelated titles ("Blaster", "Black Zacian", "Black
# Star Promo"). Requiring the full "Black Label" / "Blk Label" /
# "Pristine 10" phrase keeps precision high; a few no-keyword Black
# Label listings will slip into the regular bgs10 bucket, which is
# acceptable — they're the same physical grade.
_BGS_BLACK_LABEL_RE = re.compile(
    r"\b(?:black\s*label|blk\s*label|pristine\s*10)\b",
    re.IGNORECASE,
)
# TAG Grading — must be followed by grade number to avoid false-
# matching "tag team" cards, "auto tag", etc. Requires immediate
# grade digit (optionally with common separators) after the token.
_TAG_RE = re.compile(
    r"\bT\.?\s*A\.?\s*G\.?\s*[-:# ]?\s*(\d{1,2}(?:\.\d)?)\b",
    re.IGNORECASE,
)
# Other graders — SGC / GMA / ACE / ISA. Grouped so we can shortcut
# to 'other' when they appear.
_OTHER_GRADER_RE = re.compile(
    r"\b(?:S\.?G\.?C\.?|G\.?M\.?A\.?|A\.?C\.?E\.?|I\.?S\.?A\.?)\b\s*[-:# ]?\s*\d",
    re.IGNORECASE,
)
# Fuzzy "grade N" without any grader abbreviation.
_BARE_GRADE_RE = re.compile(r"\bgrade\s*\d", re.IGNORECASE)

# Sellers of RAW cards routinely invoke a grade they hope the card
# would earn — "PSA 10 potential!", "PSA10 Contender", "BGS 9.5
# worthy", "ready to grade". Read literally those titles land in a
# graded bucket, which both mislabels the Live-listings Graded tab and
# drags slab medians down toward raw prices (a $345 "PSA 10 potential"
# raw sitting in the same median as real $1,500 slabs).
#
# Anything matching here is forced back to 'raw' before grader
# detection runs. Deliberately conservative: every marker below is
# language a genuine slab listing has no reason to use. Note "gem
# mint" is NOT here — that's standard slab nomenclature ("PSA 10 GEM
# MINT"), and treating it as aspirational would reject real slabs.
_ASPIRATIONAL_RE = re.compile(
    r"\b(?:"
    r"potential|contender|candidate|worthy|grade-?able"
    r"|(?:would|should|could|will|might)\s+(?:easily\s+)?grade"
    r"|ready\s+to\s+grade|for\s+grading|to\s+be\s+graded|pre-?grade"
    r"|(?:psa|bgs|cgc|sgc|tag)\s*\d*(?:\.\d)?\s*"
    r"(?:ready|material|quality|hopeful|bound)"
    r")\b",
    re.IGNORECASE,
)

# Explicit denials. Kept separate and narrow — matching a grader name
# after a negation word ("PSA 10, not BGS") would be a false positive,
# so only phrasings that negate grading itself are listed.
_NOT_GRADED_RE = re.compile(
    r"\bun-?graded\b|\bnot\s+graded\b|\bno\s+grade\b|\bnever\s+graded\b",
    re.IGNORECASE,
)


def _bucket(prefix: str, num_str: str) -> str:
    """Map a grader + numeric grade to the canonical tier vocab."""
    try:
        num = float(num_str)
    except ValueError:
        return "other"
    # PSA uses integer grades only (10, 9, 8...); everything else is 'other'.
    if prefix == "psa":
        if num == 10:
            return "psa10"
        if num == 9:
            return "psa9"
        if num == 8:
            return "psa8"
        return "other"
    # CGC / BGS carry .5 half-grades.
    if prefix == "cgc":
        if num == 10:
            return "cgc10"
        if num == 9.5:
            return "cgc9.5"
        if num == 9:
            return "cgc9"
        return "other"
    if prefix == "bgs":
        if num == 10:
            # Black Label / Pristine 10 gets promoted at the call
            # site in classify_grade() — this bucket returns the
            # regular bgs10 by default, then the caller upgrades
            # to bgs10bl if the title also carries the Black Label
            # signal. Keeps this helper stateless.
            return "bgs10"
        if num == 9.5:
            return "bgs9.5"
        if num == 9:
            return "bgs9"
        return "other"
    if prefix == "tag":
        if num == 10:
            return "tag10"
        if num == 9.5:
            return "tag9.5"
        if num == 9:
            return "tag9"
        return "other"
    return "other"


def classify_grade(title: str) -> str:
    """Return the canonical grade tag for an eBay listing title.

    Precedence: PSA > CGC > BGS > TAG (arbitrary but stable — nearly
    no listings carry more than one grader). Other graders / off-vocab
    grades collapse to 'other'. No grader mention at all → 'raw'.

    A named grade the seller only *hopes* for ("PSA 10 potential",
    "BGS 9.5 worthy", "ready to grade") or explicitly denies
    ("ungraded") is raw — see _ASPIRATIONAL_RE / _NOT_GRADED_RE.
    """
    if not title:
        return "raw"

    # A grade the seller is *aspiring* to, or explicitly disclaiming,
    # describes a raw card no matter which grader it names.
    if _ASPIRATIONAL_RE.search(title) or _NOT_GRADED_RE.search(title):
        return "raw"

    m = _PSA_RE.search(title)
    if m:
        return _bucket("psa", m.group(1))

    # CGC Pristine 10 pattern first — "CGC 10" regex would fail on
    # "CGC PRISTINE 10" (needs digit adjacent to CGC) so we check
    # the pristine-specific pattern before falling to the general
    # one. Otherwise the listing would leak into 'raw' and blow
    # right past our graded-price filter.
    if _CGC_PRISTINE_RE.search(title):
        return "cgc10"

    m = _CGC_RE.search(title)
    if m:
        return _bucket("cgc", m.group(1))

    m = _BGS_RE.search(title)
    if m:
        bucket = _bucket("bgs", m.group(1))
        # Promote BGS 10 to Black Label when the listing carries
        # the marker keywords. Only applies to grade 10 (Black
        # Label doesn't exist below BGS 10).
        if bucket == "bgs10" and _BGS_BLACK_LABEL_RE.search(title):
            return "bgs10bl"
        return bucket

    # Beckett synonym — routes to the same bgs* buckets. Checked
    # AFTER _BGS_RE so a "Beckett BGS 9.5" listing (both keywords)
    # picks up the primary BGS match first, which is fine either
    # way since they resolve to the same tier.
    m = _BECKETT_RE.search(title)
    if m:
        bucket = _bucket("bgs", m.group(1))
        if bucket == "bgs10" and _BGS_BLACK_LABEL_RE.search(title):
            return "bgs10bl"
        return bucket

    m = _TAG_RE.search(title)
    if m:
        return _bucket("tag", m.group(1))

    if _OTHER_GRADER_RE.search(title):
        return "other"

    if _BARE_GRADE_RE.search(title):
        return "other"

    return "raw"
