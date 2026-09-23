---
profile: market
schema: 1
layer: mls                            # built-in layer: used when the MLS is Stellar
name: Stellar MLS
mls: Stellar
aliases: [Stellar MLS, My Florida Regional MLS, MFRMLS]
as_of: 2026

# Where Stellar is the MLS. Counties are inferred from the shareholder associations at
# https://www.stellarmls.com/about/shareholders (2026). Stellar's coverage map is authoritative;
# a county missing here only means the MLS isn't assumed without asking.
coverage:
  FL: [Alachua, Charlotte, Citrus, DeSoto, Flagler, Hernando, Hillsborough, Lake, Manatee, Marion,
       Orange, Osceola, Pasco, Polk, Sarasota, Seminole, Sumter, Volusia]
  PR: all
associations:
  shareholders:
    - Bartow Board of REALTORS®, Inc. (BBOR)
    - East Polk County Association of REALTORS® (EPCAR)
    - Lakeland REALTORS® (LAR)
    - REALTORS® Association of Lake & Sumter Counties (RALSC)
    - Orlando Regional REALTOR® Association (ORRA)
    - Osceola County Association of REALTORS® (OSCAR)
    - West Volusia Association of REALTORS® (WVAR)
    - Suncoast Tampa Association of REALTORS® (STAR)
    - Englewood Area Board of REALTORS® (EABOR)
    - REALTORS® of Punta Gorda-Port Charlotte-North Port-DeSoto, Inc.® (PGPCNP)
    - REALTOR® Association of Sarasota & Manatee (RASM)
    - Venice Area Board of REALTORS® (VABR)
    - West Pasco Hernando REALTORS® (WPHR)
    - Ocala Marion County Association of REALTORS® (OMCAR)
    - Gainesville-Alachua County Association of REALTORS® (GACAR)
    - Flagler County Association of REALTORS® (FCAR)
    - New Smyrna Beach Board of REALTORS® (NSBBOR)
    - REALTORS® Association of Citrus County (RACC)
  customers:
    - Lake Wales Association of REALTORS® (LWAR)
    - Puerto Rico Association of REALTORS® (PRAR)

mls_format:
  history_codes:
    NEW: New listing
    DECR: Price decrease
    INCR: Price increase
    TOM: Temporarily off market
    BOM: Back on market
    PNC: Pending (under contract)
    SLD: Sold
    CANC: Canceled
    EXP: Expired
    WDN: Withdrawn
  cma_export_columns:
    distance: Distance
    mls_number: ML Number
    status: Status
    address: Address
    subdivision: Legal Subdivision Name
    living_area: Heated Area
    current_price: Current Price
    close_price: Close Price
    close_date: Close Date
    original_list_price: Original List Price
    contract_date: Contract Date
    beds: Beds
    full_baths: Full Baths
    year_built: Year Built
    pool: Pool
    days_on_market: CDOM
    seller_paid_buyer_costs: Seller Paid Buyer Costs
    lot_acres: Lot Size Acres
    sale_terms: Sold Terms
    remarks: Public Remarks
---

# Market profile layer: Stellar MLS

Built-in MLS formats. Used whenever the MLS is Stellar, in any state it serves (Florida and Puerto Rico). State costs and rules come from the state layer, never from here.

## Notes

- Reading the history grid: newest first, so read bottom to top. A new MLS number resets days on market; look for an older number below it. Report the true timeline: first list date, total active days across listings (sum of CDOM), every price change, and any failed contract.
- PNC followed by TOM, BOM or CANC instead of SLD means the contract failed.
- Repeated TOM/BOM pairs often mean a seller managing showings or pausing to reset.
- A cancel followed by NEW is a relist that resets the day count.
