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
       Orange, Osceola, Pasco, Pinellas, Polk, Sarasota, Seminole, Sumter, Volusia]
  # Pinellas: Suncoast Tampa (STAR) is a shareholder (verified 2026-09-24). Not Stellar: Brevard (Space Coast MLS),
  # Miami-Dade, Broward and Palm Beach (MIAMI MLS / BeachesMLS). Without a county, no MLS is assumed.
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
  # Field name: accepted headers. Stellar exports use the standard (RESO) field names; older Matrix exports
  # use the display labels listed after them. Only address, status, living_area, close_price and
  # current_price are required; the rest make the comp ranking and summaries better when present.
  cma_export_columns:
    mls_number: [ListingId, ML Number, MLS Number]
    status: [MlsStatus, Status]
    address: [UnparsedAddress, Address]
    unit: [UnitNumber, Unit Number]
    zip: [PostalCode, Zip]
    subdivision: [SubdivisionName, Legal Subdivision Name]
    distance: [Distance]
    latitude: [Latitude]
    longitude: [Longitude]
    original_list_price: [OriginalListPrice, Original List Price]
    current_price: [ListPrice, Current Price]
    close_price: [ClosePrice, Close Price]
    contract_date: [PurchaseContractDate, Contract Date]
    close_date: [CloseDate, Close Date]
    days_on_market: [CumulativeDaysOnMarket, CDOM]
    sale_terms: [BuyerFinancing, Sold Terms]
    seller_paid_buyer_costs: [ConcessionsAmount, Seller Paid Buyer Costs]
    sale_provisions: [SpecialListingConditions, Special Sale Provision(s)]
    new_construction: [NewConstructionYN, New Construction YN]
    property_type: [PropertySubType, Property Style]
    living_area: [LivingArea, Heated Area]
    beds: [BedroomsTotal, Beds]
    full_baths: [BathroomsFull, Full Baths]
    half_baths: [BathroomsHalf, Half Baths]
    stories: [Levels, Floors in Unit/Home]
    floor_number: [FloorNumber, Floor Number]
    year_built: [YearBuilt, Year Built]
    construction: [ConstructionMaterials, Exterior Construction]
    garage_spaces: [GarageSpaces, Garage Spaces]
    pool: [PoolPrivateYN, Pool Private Y/N, Pool]
    furnished: [Furnished, Furnishings]
    lot_acres: [LotSizeAcres, Lot Size Acres]
    waterfront: [WaterfrontYN, Water Frontage Y/N]
    water_frontage: [WaterfrontFeatures, Water Frontage]
    water_access: [WaterAccess, Water Access]
    water_view: [WaterViewYN, Water View Y/N]
    sewer: [Sewer]
    water_source: [WaterSource, Water]
    flood_zone: [FloodZoneCode, Flood Zone Code]
    senior_community: [SeniorCommunityYN, Housing for Older Persons Y/N]
    land_lease: [LandLeaseYN, Land Lease Y/N]
    total_annual_fees: [TotalAnnualFees, Total Annual Association Fees]
    annual_cdd_fee: [AnnualCDDFee, Annual CDD Fee]
    remarks: [PublicRemarks, Public Remarks]
    sold_remarks: [SoldRemarks, Sold Remarks]
---

# Market Layer: Stellar MLS

Built-in MLS formats. Used whenever the MLS is Stellar, in any state it serves (Florida and Puerto Rico). State costs and rules come from the state layer, never from here.

## Notes

- Reading the history grid: newest first, so read bottom to top. A new MLS number resets days on market; look for an older number below it. Report the true timeline: first list date, total active days across listings (sum of CDOM), every price change, and any failed contract.
- PNC followed by TOM, BOM or CANC instead of SLD means the contract failed.
- Repeated TOM/BOM pairs often mean a seller managing showings or pausing to reset.
- A cancel followed by NEW is a relist that resets the day count.

## CMA Export

- The export holds the property types the agent wants compared. Single-family homes and townhouses can sit together when they overlap in size and price; the ranking favors the subject's type without dropping the others.
- A zip or subdivision search has no Distance column: the scripts measure miles from Latitude and Longitude, starting at the subject's own row.
- The same closing can appear twice (a "Sold Data Entry Only" copy, often an MLS number starting with J). The scripts keep one.
- A relisted home shows once in the competition, with how many times it was listed and its earlier prices.
- Fees: TotalAnnualFees is the annual total. AssociationFee is left out because its period varies by listing.
- Lot size is ignored for condos, and flood zone codes are cleaned up ("X*" reads X; "Yes (X, X500, Ae)" reads AE, the riskiest).
