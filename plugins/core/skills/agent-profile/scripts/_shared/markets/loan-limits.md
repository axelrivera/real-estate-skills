---
profile: loan_limits
year: 2026
as_of: "2026-09-24"
sources:
  conforming: "FHFA, 2026 conforming loan limits (county file)"
  fha: "HUD Mortgagee Letter 2025-23 (2026 FHA forward mortgage limits)"
conforming:                       # one-unit limits
  baseline: 832750
  ceiling: 1249125                # high-cost areas
fha:
  floor: 541287
  ceiling: 1249125
counties:                         # one-unit limits above the baseline or floor, by state and county
  FL:
    Monroe: {conforming: 990150}  # FHA county limits above the floor in Florida aren't loaded yet: confirm with the lender
---

# Loan Limits

National loan limits for the offer skills' checks, refreshed every year (FHFA and HUD publish them in late November for the next year). A county not listed uses the baseline (conforming) or floor (FHA); in a high-cost county outside Florida the limit can be higher, so an amount above the baseline is flagged for the lender to confirm, not treated as a fact.
