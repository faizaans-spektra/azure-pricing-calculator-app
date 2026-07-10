# Azure Pricing Calculator Automation

A Streamlit application that ingests Azure Excel exports, screenshots, and ARM templates, then estimates monthly resource costs using the Azure Retail Prices API.

## Features

- Upload Excel with Azure resources and SKUs
- Upload screenshot of an Excel sheet and OCR resource rows
- Upload ARM template JSON or paste ARM JSON
- Extract Azure VM, disk, firewall, storage, SQL, App Service, Application Gateway, Public IP, Load Balancer, and Log Analytics resources
- Compare pricing across regions
- Export results to Excel

## Run

1. Create a Python virtual environment
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run Streamlit:
   ```bash
   streamlit run app.py
   ```

## Notes

- Pricing data is sourced from the Azure Retail Prices API: `https://prices.azure.com/api/retail/prices`
- The app aims to match Azure Pricing Calculator monthly pricing behavior, with best-effort SKU normalization and fuzzy matching.
