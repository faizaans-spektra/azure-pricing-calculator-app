**What This App Is**
It is a Streamlit-based Azure cost estimation app that reads ARM JSON, Excel, or screenshots, identifies Azure resources, and estimates monthly pricing using the Azure Retail Prices API.  
It is designed to reduce manual effort for infrastructure cost comparison across regions, especially for hard resources like VM, managed disks, Public IP, App Service, SQL, and storage.

**What The Code Contains**
1. Main application logic and UI: app.py
2. Usage/setup notes: README.md
3. Pricing/parser test scripts: test_arm_parse.py, test_arm_pricing.py
4. Debug probes for API/resource matching: files starting with debug_*.py in the project root

Inside app.py, the core parts are:
1. Input parsing for Excel/ARM/screenshot
2. ARM normalization to resource rows (type, SKU, region, OS, size, hours)
3. Service-specific pricing resolvers using Azure Retail Prices API
4. Auto-enrichment (fills missing fields automatically, no forced manual prompts)
5. Result table with confidence, assumptions, and total cost calculations

**How It Was Built (In Practical Terms)**
1. Started from a generic SKU-match pricing engine
2. Added deterministic VM pricing (Windows/Linux, Spot/DevTest filtering)
3. Improved managed disk and Public IP matching to avoid wrong meters
4. Added ARM expression resolution (parameters/variables) for better extraction
5. Added auto-enrichment so missing required fields are inferred instead of asking users
6. Separated monitoring impact from hard-resource totals so core infra totals stay reliable

**Questions & Answers**

1. What is it?
A lightweight internal Azure pricing estimator that reads ARM/Excel and auto-calculates monthly infra cost.

2. How accurate is it?
Strong for hard resources (VM, disk, IP, app service, SQL, storage), and improving; monitoring costs are intentionally treated separately to avoid skewed infra totals.

3. How does it work?
It parses resources, normalizes SKU/type/region/OS/size, queries Azure Retail Prices API, applies service-specific matching rules, and returns per-resource and regional totals.

4. What value does it give?
Faster pre-sales/design estimates, reduced manual calculator work, and transparent assumptions/confidence per line item.

