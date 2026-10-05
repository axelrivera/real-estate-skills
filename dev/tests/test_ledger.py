"""finance.Ledger: every printed column adds up, for any lines (generated)."""
import os
import random
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import finance, fmt, profiles  # noqa: E402


def printed(text):
    neg = text.startswith(fmt.MINUS) or text.startswith("(")
    v = int(re.sub(r"[^\d]", "", text))
    return -v if neg else v


def random_ledger(rng):
    led = finance.Ledger()
    price = rng.randint(80_000, 3_000_000) + rng.choice([0, 0.5, rng.random()])
    led.add("price", "Sale Price", price)
    for i in range(rng.randint(0, 14)):
        amount = rng.choice([price * rng.uniform(0, 0.06), rng.randint(0, 5000) + 0.5, rng.uniform(0, 900)])
        if rng.random() < 0.15:
            led.credit(f"credit{i}", f"Credit {i}", amount)
        else:
            led.cost(f"line{i}", f"Line {i}", amount)
    return led


class LedgerProperties(unittest.TestCase):
    def test_total_is_the_sum_of_printed_lines(self):
        rng = random.Random(1)
        for _ in range(2000):
            led = random_ledger(rng)
            rows = led.rows()
            self.assertEqual(sum(printed(t) for _, t in rows), led.total())
            self.assertEqual(printed(fmt.money(led.total())), led.total())
            # the cost column printed as positive numbers adds to costs()
            costs = [printed(t) for (_, t), ln in zip(led.rows(sign=False), led) if ln["amount"] < 0]
            self.assertEqual(sum(costs), led.costs())

    def test_lines_rounded_once_half_up(self):
        rng = random.Random(2)
        for _ in range(500):
            led = random_ledger(rng)
            for ln in led:
                self.assertIsInstance(ln["amount"], int)
                self.assertEqual(ln["amount"], fmt.half_up(ln["raw"]))
                self.assertLessEqual(abs(ln["amount"] - ln["raw"]), 0.5)

    def test_signs(self):
        rng = random.Random(3)
        for _ in range(1000):
            a = rng.randint(0, 100000) + rng.choice([0, 0.5, 0.25, 0.75])
            led = finance.Ledger()
            self.assertEqual(led.cost("c", "C", a), -led.credit("d", "D", a))
            self.assertEqual(led.total(), 0)
            self.assertEqual(led.costs(), fmt.half_up(a))

    def test_subtotals_partition_the_total(self):
        rng = random.Random(4)
        for _ in range(500):
            led = random_ledger(rng)
            keys = {ln["key"] for ln in led}
            some = set(rng.sample(sorted(keys), rng.randint(0, len(keys))))
            self.assertEqual(led.total(keys=some) + led.total(keys=keys - some), led.total())

    def test_amount_and_tuples(self):
        led = finance.Ledger([("price", "Price", 400_000), ("fee", "Fee", -1234.5)])
        self.assertEqual(led.amount("fee"), -1235)
        self.assertEqual(led.amount("missing", None), None)
        self.assertEqual(led.tuples(), [("price", "Price", 400_000), ("fee", "Fee", -1235)])
        self.assertTrue(led.has("price") and not led.has("x"))

    def test_rejects_non_numbers(self):
        with self.assertRaises(TypeError):
            finance.Ledger().add("x", "X", "1,000")
        with self.assertRaises(TypeError):
            finance.Ledger().add("x", "X", True)


class SellerNetAdapter(unittest.TestCase):
    def test_net_from_rounded_lines(self):
        market = profiles.load_market(state="FL", county="Orange")
        rng = random.Random(5)
        for _ in range(200):
            price = rng.randint(150_000, 2_500_000)
            payoff = rng.choice([None, rng.randint(0, price // 2)])
            net = finance.seller_net(price, market, credit=rng.choice([0, 5000]), payoff=payoff, has_hoa=rng.random() < 0.5)
            led = finance.seller_net_ledger(price, net, payoff)
            self.assertEqual(sum(printed(t) for _, t in led.rows()), led.total())
            self.assertLessEqual(abs(led.total() - (net["net"] if payoff else net["net_before_payoff"])), len(led))


if __name__ == "__main__":
    unittest.main()
