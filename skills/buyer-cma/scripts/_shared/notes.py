"""One notes registry per document: every assumption, estimate and caveat is added once, by key, and printed once.

    from _shared import notes
    N = notes.Notes()
    N.add("commission", "Commission is assumed at 5% total.", kind="assumption")
    N.add("title", "Owner's title is an estimate from the published rate.", kind="estimate")
    N.add("form", "Contract read as the AS IS form.", kind="chat_only")
    N.pdf()        # the texts for the report's notes block, in order (no chat_only ones)
    N.chat()       # every text, chat_only included, for the reply
    N.label_problems(["Listing Brokerage (5%)", ...])   # [] when no label carries a note

A key added twice keeps its first text (the second add is a no-op), and so does the same text under a second key,
so a note can never print twice. Labels never carry notes: a label that contains a note's text, or tags itself
"(Estimate)" / "(Assumed)", is a construction error (label_problems / check_labels).
"""
import re

KINDS = ("assumption", "estimate", "info", "chat_only")
# The order the notes block prints in: what was assumed, then what is estimated, then the rest.
ORDER = {"assumption": 0, "estimate": 1, "info": 2, "chat_only": 3}
# A label tagged as a note: "(Estimate)", "(Assumed)", "(Est.)", "Title Fees, Assumed", "Tax – Estimate". Plain words
# in a heading ("Estimated Net Proceeds") are a label's name, not a tag.
_LABEL_TAG = re.compile(r"\(\s*(?:est\.?|estimated?|assumed|assumption)\s*\)|[,–-]\s*(?:estimated?|assumed)\s*$", re.I)


class NotesError(ValueError):
    pass


def _squash(text):
    return " ".join(str(text).split()).casefold().rstrip(".")


class Notes:
    def __init__(self):
        self._items = []  # [(key, text, kind)]

    def add(self, key, text, kind="info"):
        """Add a note once. Returns True when it was added, False when the key (or the same text) is already here."""
        if kind not in KINDS:
            raise NotesError(f"note kind {kind!r} isn't one of {', '.join(KINDS)}")
        text = " ".join(str(text or "").split())
        if not text:
            return False
        if any(k == key or _squash(t) == _squash(text) for k, t, _ in self._items):
            return False
        self._items.append((key, text, kind))
        return True

    def __contains__(self, key):
        return any(k == key for k, _, _ in self._items)

    def __len__(self):
        return len(self._items)

    def get(self, key):
        return next((t for k, t, _ in self._items if k == key), None)

    def items(self, where="pdf", grouped=True):
        """[(key, text, kind)] for "pdf" (no chat_only notes) or "chat" (all of them): grouped by kind (assumptions,
        estimates, other notes), in the order they were added within each kind; grouped=False keeps the add order."""
        out = [it for it in self._items if where == "chat" or it[2] != "chat_only"]
        return sorted(out, key=lambda it: ORDER[it[2]]) if grouped else out

    def pdf(self, grouped=True):
        return [t for _, t, _ in self.items("pdf", grouped)]

    def chat(self, grouped=True):
        return [t for _, t, _ in self.items("chat", grouped)]

    def texts(self, kind):
        return [t for _, t, k in self._items if k == kind]

    def label_problems(self, labels):
        """[(label, why)] for labels that carry a note: one containing a note's text, or one tagged Estimate /
        Assumed (a report says that once, in its notes, never in a label)."""
        out = []
        notes = [_squash(t) for _, t, _ in self._items]
        for label in labels:
            s = _squash(label)
            if not s:
                continue
            if _LABEL_TAG.search(str(label)):
                out.append((label, "tags itself as an estimate or assumption"))
            elif any(n and n in s for n in notes):
                out.append((label, "carries a note's text"))
        return out

    def check_labels(self, labels):
        """Raise NotesError naming every label that carries a note."""
        found = self.label_problems(labels)
        if found:
            raise NotesError("Labels never carry notes: " + "; ".join(f"{label!r} {why}" for label, why in found))
