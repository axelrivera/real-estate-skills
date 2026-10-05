"""notes.Notes: each note printed once, in a fixed order, never in a label (generated adds)."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import notes  # noqa: E402

WORDS = "price title tax fee commission closing survey estoppel payoff insurance rate credit".split()


def random_notes(rng, n=30):
    N, added = notes.Notes(), []
    for _ in range(n):
        key = rng.choice(WORDS[:8])
        text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 8))).capitalize() + "."
        if rng.random() < 0.2 and added:  # the same text again under another key, or with other spacing and case
            text = rng.choice(added).upper().replace(" ", "  ")
        kind = rng.choice(notes.KINDS)
        if N.add(key, text, kind):
            added.append(text)
    return N


class Registry(unittest.TestCase):
    def test_each_key_and_text_once(self):
        rng = random.Random(1)
        for _ in range(500):
            N = random_notes(rng)
            items = N.items("chat", grouped=False)
            self.assertEqual(len({k for k, _, _ in items}), len(items))
            squashed = [" ".join(t.split()).casefold() for _, t, _ in items]
            self.assertEqual(len(set(squashed)), len(squashed))

    def test_first_add_wins(self):
        N = notes.Notes()
        self.assertTrue(N.add("a", "First.", "estimate"))
        self.assertFalse(N.add("a", "Second.", "assumption"))
        self.assertFalse(N.add("b", "  first ", "info"))
        self.assertFalse(N.add("c", "", "info"))
        self.assertEqual(N.get("a"), "First.")
        self.assertEqual(len(N), 1)

    def test_order_and_where(self):
        rng = random.Random(2)
        for _ in range(300):
            N = random_notes(rng)
            pdf, chat = N.items("pdf"), N.items("chat")
            self.assertNotIn("chat_only", [k for _, _, k in pdf])
            self.assertEqual([t for _, t, k in chat if k != "chat_only"], [t for _, t, _ in pdf])
            ranks = [notes.ORDER[k] for _, _, k in chat]
            self.assertEqual(ranks, sorted(ranks))
            # within a kind, the order they were added
            raw = N.items("chat", grouped=False)
            for kind in notes.KINDS:
                self.assertEqual([t for _, t, k in chat if k == kind], [t for _, t, k in raw if k == kind])
            self.assertEqual(N.pdf(), [t for _, t, _ in pdf])

    def test_unknown_kind(self):
        with self.assertRaises(notes.NotesError):
            notes.Notes().add("a", "Text.", kind="warning")


class Labels(unittest.TestCase):
    def test_a_label_never_carries_a_note(self):
        rng = random.Random(3)
        for _ in range(300):
            N = random_notes(rng, 10)
            texts = N.chat()
            note = rng.choice(texts)
            clean = [w.title() for w in rng.sample(WORDS, 4)]
            self.assertEqual(N.label_problems(clean), [])
            carrying = f"{rng.choice(clean)} ({note.rstrip('.')})"
            self.assertEqual([lb for lb, _ in N.label_problems(clean + [carrying])], [carrying])
            with self.assertRaises(notes.NotesError):
                N.check_labels([carrying])

    def test_estimate_tags(self):
        N = notes.Notes()
        for tagged in ("Owner's Title (Estimate)", "Title Fees (Assumed)", "Survey (est.)", "Tax, Estimated",
                       "HOA Documents – Assumed"):
            self.assertTrue(N.label_problems([tagged]), tagged)
        for name in ("Estimated Net Proceeds", "Estimated Monthly Payment", "Listing Brokerage (5%)"):
            self.assertEqual(N.label_problems([name]), [], name)


if __name__ == "__main__":
    unittest.main()
