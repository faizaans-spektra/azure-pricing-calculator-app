import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
from rapidfuzz import fuzz

try:
    import easyocr
except ImportError:
    easyocr = None

DEFAULT_REGIONS = ["East US", "UAE North", "Central India", "West Europe"]
AZURE_PRICING_API = "https://prices.azure.com/api/retail/prices"
MONTHLY_HOURS_DEFAULT = 730

SUPPORTED_RESOURCE_TYPES = {
    "virtualmachines": "Virtual Machine",
    "disks": "Managed Disk",
    "azurefirewalls": "Azure Firewall",
    "storageaccounts": "Storage Account",
    "sqlservers/databases": "SQL Database",
    "sqlservers": "SQL Database",
    "databases": "SQL Database",
    "web/sites": "App Service",
    "sites": "App Service",
    "serverfarms": "App Service",
    "applicationgateways": "Application Gateway",
    "publicipaddresses": "Public IP",
    "loadbalancers": "Load Balancer",
    "workspaces": "Log Analytics",
    "networkinterfaces": "Network Interface",
    "virtualnetworks": "Virtual Network",
    "networksecuritygroups": "Network Security Group",
    "publicipaddresses": "Public IP",
    "storageaccounts": "Storage Account",
    "containers": "Container",
    "containerinstances": "Container Instance",
    "manageddisks": "Managed Disk",
}

COLUMN_ALIASES = {
    "resource type": "resourceType",
    "resource_type": "resourceType",
    "type": "resourceType",
    "sku": "sku",
    "vm size": "sku",
    "quantity": "quantity",
    "qty": "quantity",
    "region": "region",
    "location": "region",
    "disk type": "diskType",
    "disk_type": "diskType",
    "disk size": "diskSize",
    "disk_size": "diskSize",
    "os": "os",
    "tier": "tier",
    "hours": "hours",
    "notes": "notes",
}

RESOURCE_TYPE_SHORTCUTS = {
    "vm": "Virtual Machine",
    "virtual machine": "Virtual Machine",
    "virtualmachines": "Virtual Machine",
    "managed disk": "Managed Disk",
    "disk": "Managed Disk",
    "firewall": "Azure Firewall",
    "storage": "Storage Account",
    "sql": "SQL Database",
    "app service": "App Service",
    "application gateway": "Application Gateway",
    "public ip": "Public IP",
    "load balancer": "Load Balancer",
    "log analytics": "Log Analytics",
    "application insights": "Application Insights",
}

MONITORING_RESOURCES = {
    "Log Analytics",
    "Application Insights",
}

SERVICE_FILTERS = {
    "Virtual Machine": "Virtual Machines",
    "Managed Disk": "Storage",
    "Storage Account": "Storage",
    "SQL Database": "SQL Database",
    "App Service": "Azure App Service",
    "Application Gateway": "Application Gateway",
    "Azure Firewall": "Azure Firewall",
    "Public IP": "Virtual Network",
    "Load Balancer": "Networking",
    "Log Analytics": "Log Analytics",
    "Application Insights": "Azure Monitor",
}

# Keep strict matching for compute-like services, but allow intelligent fallback
# for services where the retail API meter/sku strings are often non-exact.
STRICT_FALLBACK_SERVICES = {
    "Managed Disk",
    "Storage Account",
    "Public IP",
    "Load Balancer",
    "Application Gateway",
    "Azure Firewall",
    "Log Analytics",
}


@dataclass
class PriceMatch:
    item: Dict[str, Any]
    confidence: int
    reason: str


@st.cache_data(show_spinner=False)
def fetch_retail_prices(filter_text: str, page_url: Optional[str] = None) -> Dict[str, Any]:
    params = {"$filter": filter_text}
    if page_url:
        response = requests.get(page_url, timeout=30)
    else:
        response = requests.get(AZURE_PRICING_API, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def query_retail_prices(filter_text: str, max_records: int = 200) -> List[Dict[str, Any]]:
    prices = []
    next_link = None
    page = 0
    payload = fetch_retail_prices(filter_text)
    prices.extend(payload.get("Items", []))
    next_link = payload.get("NextPageLink")
    while next_link and len(prices) < max_records and page < 10:
        payload = fetch_retail_prices(filter_text, page_url=next_link)
        prices.extend(payload.get("Items", []))
        next_link = payload.get("NextPageLink")
        page += 1
    return prices


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def standardize_resource_type(value: str) -> str:
    normalized = normalize_text(value).lower().replace(" ", "").replace("_", "")
    if not normalized:
        return "Unknown"
    if normalized in RESOURCE_TYPE_SHORTCUTS:
        return RESOURCE_TYPE_SHORTCUTS[normalized]
    for key, name in SUPPORTED_RESOURCE_TYPES.items():
        if key in normalized:
            return name
    for key, name in RESOURCE_TYPE_SHORTCUTS.items():
        if key.replace(" ", "") in normalized:
            return name
    return normalize_text(value)


def normalize_vm_sku(sku: str) -> str:
    sku_text = normalize_text(sku)
    if not sku_text:
        return ""
    sku_text = sku_text.replace("Standard_", "").replace("standard_", "")
    sku_text = sku_text.replace("_", " ").replace("-", " ")
    sku_text = re.sub(r"\s+", " ", sku_text).strip()
    sku_text = re.sub(r"^(ds|dsv|d)", lambda m: m.group(0).upper(), sku_text, flags=re.IGNORECASE)
    return sku_text


def normalize_disk_sku(sku: str) -> str:
    sku_text = normalize_text(sku)
    if not sku_text:
        return ""
    parts = re.split(r"[\,\|;/]+", sku_text)
    if len(parts) > 1:
        for part in parts:
            candidate = normalize_disk_sku(part)
            if candidate:
                return candidate
        return normalize_text(parts[0])

    sku_text = sku_text.lower().replace("_", " ").replace("-", " ")
    sku_text = re.sub(r"\s+", " ", sku_text).strip()

    if "premium ssd v2" in sku_text:
        return "Premium SSD v2"
    if "premium lrs" in sku_text or ("premium" in sku_text and "managed" in sku_text):
        return "Premium SSD Managed Disks"
    if sku_text.startswith("p") and sku_text[1:].isdigit():
        return sku_text.upper()
    if "standard ssd" in sku_text or "standardssd" in sku_text:
        return "Standard SSD Managed Disks"
    if "standard hdd" in sku_text or ("standard" in sku_text and "hdd" in sku_text):
        return "Standard HDD Managed Disks"
    if "standard lrs" in sku_text and "ssd" not in sku_text:
        return "Standard HDD Managed Disks"
    if "ultra" in sku_text:
        return "Ultra Disk"

    return normalize_text(sku)


def disk_tier_from_size(disk_type: str, size_gb: float) -> str:
    disk_text = normalize_text(disk_type).lower()
    if size_gb <= 0:
        return ""

    premium_thresholds = [
        (4, "P1"),
        (8, "P2"),
        (16, "P3"),
        (32, "P4"),
        (64, "P6"),
        (128, "P10"),
        (256, "P15"),
        (512, "P20"),
        (1024, "P30"),
        (2048, "P40"),
        (4096, "P50"),
        (8192, "P60"),
        (16384, "P70"),
        (32767, "P80"),
    ]
    ssd_thresholds = [
        (4, "E1"),
        (8, "E2"),
        (16, "E3"),
        (32, "E4"),
        (64, "E6"),
        (128, "E10"),
        (256, "E15"),
        (512, "E20"),
        (1024, "E30"),
        (2048, "E40"),
        (4096, "E50"),
        (8192, "E60"),
        (16384, "E70"),
        (32767, "E80"),
    ]
    hdd_thresholds = [
        (32, "S4"),
        (64, "S6"),
        (128, "S10"),
        (256, "S15"),
        (512, "S20"),
        (1024, "S30"),
        (2048, "S40"),
        (4096, "S50"),
        (8192, "S60"),
        (16384, "S70"),
        (32767, "S80"),
    ]

    if "premium" in disk_text:
        thresholds = premium_thresholds
    elif "standard ssd" in disk_text:
        thresholds = ssd_thresholds
    elif "standard hdd" in disk_text or "hdd" in disk_text:
        thresholds = hdd_thresholds
    else:
        return ""

    for threshold, tier in thresholds:
        if size_gb <= threshold:
            return tier
    return thresholds[-1][1]


def normalize_os(value: str) -> str:
    text = normalize_text(value).lower()
    if "windows" in text:
        return "Windows"
    if "linux" in text:
        return "Linux"
    if "unix" in text:
        return "Linux"
    return normalize_text(value)


def normalize_app_service_sku(sku: str) -> str:
    sku_text = normalize_text(sku)
    if not sku_text:
        return ""
    if re.match(r"^[PSI]\d+v\d+$", sku_text, flags=re.IGNORECASE):
        return re.sub(r"([A-Za-z]+\d+)(v\d+)", r"\1 \2", sku_text, flags=re.IGNORECASE)
    return sku_text


def normalize_sql_sku(value: str) -> str:
    sku_text = normalize_text(value)
    if not sku_text:
        return ""
    match = re.match(r"GP_Gen5_(\d+)$", sku_text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} vCore"
    match = re.match(r"BC_Gen5_(\d+)$", sku_text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} vCore"
    match = re.search(r"(\d+)\s*vcore", sku_text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} vCore"
    return sku_text


REGION_NAME_MAP = {
    "east us": "eastus",
    "eastus": "eastus",
    "east us 2": "eastus2",
    "eastus2": "eastus2",
    "east us 3": "eastus3",
    "eastus3": "eastus3",
    "central us": "centralus",
    "centralus": "centralus",
    "north central us": "northcentralus",
    "northcentralus": "northcentralus",
    "south central us": "southcentralus",
    "southcentralus": "southcentralus",
    "west us": "westus",
    "westus": "westus",
    "west us 2": "westus2",
    "westus2": "westus2",
    "west us 3": "westus3",
    "westus3": "westus3",
    "canada east": "canadaeast",
    "canadaeast": "canadaeast",
    "canada central": "canadacentral",
    "canadacentral": "canadacentral",
    "brazil south": "brazilsouth",
    "brazilsouth": "brazilsouth",
    "brazil southeast": "brazilsoutheast",
    "brazilsoutheast": "brazilsoutheast",
    "france central": "francecentral",
    "francecentral": "francecentral",
    "france south": "francesouth",
    "francesouth": "francesouth",
    "germany north": "germanynorth",
    "germanynorth": "germanynorth",
    "germany west central": "germanywestcentral",
    "germanywestcentral": "germanywestcentral",
    "norway east": "norwayeast",
    "norwayeast": "norwayeast",
    "norway west": "norwaywest",
    "norwaywest": "norwaywest",
    "sweden central": "swedencentral",
    "swedencentral": "swedencentral",
    "sweden south": "swedensouth",
    "swedensouth": "swedensouth",
    "switzerland north": "switzerlandnorth",
    "switzerlandnorth": "switzerlandnorth",
    "switzerland west": "switzerlandwest",
    "switzerlandwest": "switzerlandwest",
    "uk south": "uksouth",
    "uksouth": "uksouth",
    "uk west": "ukwest",
    "ukwest": "ukwest",
    "japan east": "japaneast",
    "japaneast": "japaneast",
    "japan west": "japanwest",
    "japanwest": "japanwest",
    "korea central": "koreacentral",
    "koreacentral": "koreacentral",
    "korea south": "koreasouth",
    "koreasouth": "koreasouth",
    "south india": "southindia",
    "southindia": "southindia",
    "central india": "centralindia",
    "centralindia": "centralindia",
    "west india": "westindia",
    "westindia": "westindia",
    "southeast asia": "southeastasia",
    "southeastasia": "southeastasia",
    "east asia": "eastasia",
    "eastasia": "eastasia",
    "uae north": "uaenorth",
    "uaenorth": "uaenorth",
    "uae central": "uaecentral",
    "uaecentral": "uaecentral",
    "south africa north": "southafricanorth",
    "southafricanorth": "southafricanorth",
    "south africa west": "southafricawest",
    "southafricawest": "southafricawest",
    "qatar central": "qatarcentral",
    "qatarcentral": "qatarcentral",
    "australia east": "australiaeast",
    "australiaeast": "australiaeast",
    "australia southeast": "australiasoutheast",
    "australiasoutheast": "australiasoutheast",
    "australia central": "australiacentral",
    "australiacentral": "australiacentral",
    "australia central 2": "australiacentral2",
    "australiacentral2": "australiacentral2",
    "new zealand north": "newzealandnorth",
    "newzealandnorth": "newzealandnorth",
    "india south central": "indiasouthcentral",
    "indiasouthcentral": "indiasouthcentral",
    "jio india central": "jioindiacentral",
    "jioindiacentral": "jioindiacentral",
    "jio india west": "jioindiawest",
    "jioindiawest": "jioindiawest",
    "att dallas 1": "attdallas1",
    "attdallas1": "attdallas1",
    "att detroit 1": "attdetroit1",
    "attdetroit1": "attdetroit1",
    "att atlanta 1": "attatlanta1",
    "attatlanta1": "attatlanta1",
    "usgovvirginia": "usgovvirginia",
    "usgovtexas": "usgovtexas",
    "usgovarizona": "usgovarizona",
    "usgovzone1": "usgovzone1",
    "degovzone2": "degovzone2",
    "global": "global",
}

def normalize_region(value: str) -> str:
    if not value:
        return ""
    normalized = normalize_text(value).lower().replace("_", " ").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in REGION_NAME_MAP:
        return REGION_NAME_MAP[normalized]
    return normalized.replace(" ", "")


def maybe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def maybe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


STRICT_PRICING_MATCH = True
RUNTIME_PRICING_OPTIONS: Dict[str, Any] = {
    "default_vm_os": "Linux",
    "allow_spot": False,
    "allow_devtest": False,
    "strict_input_validation": False,
}


def runtime_option(name: str, default: Any) -> Any:
    return RUNTIME_PRICING_OPTIONS.get(name, default)


def vm_arm_sku_name(sku: str) -> str:
    sku_text = normalize_vm_sku(sku)
    if not sku_text:
        return ""
    arm = sku_text.replace(" ", "_")
    if not arm.lower().startswith("standard_"):
        arm = f"Standard_{arm}"
    return arm


def parse_effective_date(item: Dict[str, Any]) -> datetime:
    value = normalize_text(item.get("effectiveStartDate", ""))
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def vm_meter_os(item: Dict[str, Any]) -> str:
    text = " ".join(
        [
            normalize_text(item.get("productName", "")).lower(),
            normalize_text(item.get("meterName", "")).lower(),
            normalize_text(item.get("skuName", "")).lower(),
        ]
    )
    if "windows" in text:
        return "Windows"
    return "Linux"


def resolve_vm_price(
    sku: str,
    region: str,
    os_type: str,
    allow_spot: bool = False,
    allow_devtest: bool = False,
) -> Optional[PriceMatch]:
    normalized_region = normalize_region(region)
    arm_sku = vm_arm_sku_name(sku)
    filters = []
    if arm_sku:
        filters.append(build_odata_filter({"serviceName": "Virtual Machines", "armRegionName": normalized_region, "armSkuName": arm_sku}))
    sku_text = normalize_vm_sku(sku)
    if sku_text:
        filters.append(f"serviceName eq 'Virtual Machines' and armRegionName eq '{normalized_region}' and contains(skuName,'{sku_text}')")

    candidates: List[Dict[str, Any]] = []
    for filter_string in filters:
        if not filter_string:
            continue
        try:
            batch = query_retail_prices(filter_string, max_records=500)
        except Exception:
            batch = []
        if batch:
            candidates.extend(batch)

    if not candidates:
        return None

    filtered = []
    for item in candidates:
        price_type = normalize_text(item.get("type", ""))
        text = " ".join(
            [
                normalize_text(item.get("meterName", "")).lower(),
                normalize_text(item.get("skuName", "")).lower(),
                normalize_text(item.get("productName", "")).lower(),
            ]
        )
        if price_type not in {"Consumption", "DevTestConsumption"}:
            continue
        if not allow_devtest and price_type == "DevTestConsumption":
            continue
        if not allow_spot and ("spot" in text or "low priority" in text):
            continue
        filtered.append(item)

    if not filtered:
        return None

    desired_os = normalize_os(os_type)
    if desired_os:
        os_specific = [item for item in filtered if vm_meter_os(item) == desired_os]
        if os_specific:
            filtered = os_specific

    filtered.sort(
        key=lambda item: (
            bool(item.get("isPrimaryMeterRegion", False)),
            parse_effective_date(item),
            maybe_float(item.get("retailPrice", 0.0), 0.0),
        ),
        reverse=True,
    )

    item = filtered[0]
    return PriceMatch(item=item, confidence=100, reason=normalize_text(item.get("meterName", "")))


def resolve_managed_disk_price(sku: str, region: str) -> Optional[PriceMatch]:
    normalized_region = normalize_region(region)
    sku_text = normalize_text(sku)
    if not sku_text:
        return None

    filters = [
        build_odata_filter({"serviceName": "Storage", "armRegionName": normalized_region, "skuName": sku_text}),
        f"serviceName eq 'Storage' and armRegionName eq '{normalized_region}' and contains(skuName,'{sku_text}') and contains(productName,'Managed Disks')",
    ]

    candidates: List[Dict[str, Any]] = []
    for filter_string in filters:
        if not filter_string:
            continue
        try:
            batch = query_retail_prices(filter_string, max_records=400)
        except Exception:
            batch = []
        if batch:
            candidates.extend(batch)

    if not candidates:
        return None

    filtered = []
    for item in candidates:
        if normalize_text(item.get("type", "")) != "Consumption":
            continue
        meter_name = normalize_text(item.get("meterName", "")).lower()
        product_name = normalize_text(item.get("productName", "")).lower()
        uom = normalize_text(item.get("unitOfMeasure", "")).lower()
        if "managed disks" not in product_name:
            continue
        if "month" not in uom:
            continue
        if "mount" in meter_name or "operation" in meter_name or "transaction" in meter_name:
            continue
        filtered.append(item)

    if not filtered:
        return None

    wants_zrs = "zrs" in sku_text.lower()
    wants_lrs = "lrs" in sku_text.lower() or not wants_zrs

    def rank(item: Dict[str, Any]) -> Tuple[int, datetime, float]:
        meter_name = normalize_text(item.get("meterName", "")).lower()
        redundancy_bonus = 0
        if wants_lrs and "lrs" in meter_name:
            redundancy_bonus = 2
        elif wants_zrs and "zrs" in meter_name:
            redundancy_bonus = 2
        elif "lrs" in meter_name:
            redundancy_bonus = 1
        elif "zrs" in meter_name:
            redundancy_bonus = 1
        return (
            redundancy_bonus + (1 if bool(item.get("isPrimaryMeterRegion", False)) else 0),
            parse_effective_date(item),
            maybe_float(item.get("retailPrice", 0.0), 0.0),
        )

    filtered.sort(key=rank, reverse=True)
    best = filtered[0]
    return PriceMatch(item=best, confidence=100, reason=normalize_text(best.get("meterName", "")))


def resolve_storage_account_price(sku: str, tier: str, region: str) -> Optional[PriceMatch]:
    normalized_region = normalize_region(region)
    sku_text = normalize_text(sku).upper()
    tier_text = normalize_text(tier)

    redundancy = ""
    for token in ["RAGZRS", "GZRS", "RAGRS", "GRS", "ZRS", "LRS"]:
        if token in sku_text:
            redundancy = token
            break

    filters = [
        f"serviceName eq 'Storage' and armRegionName eq '{normalized_region}' and contains(meterName,'Data Stored')",
    ]
    if redundancy:
        filters.insert(0, f"serviceName eq 'Storage' and armRegionName eq '{normalized_region}' and contains(meterName,'{redundancy}') and contains(meterName,'Data Stored')")
    if tier_text:
        filters.insert(0, f"serviceName eq 'Storage' and armRegionName eq '{normalized_region}' and contains(productName,'{tier_text}') and contains(meterName,'Data Stored')")

    candidates: List[Dict[str, Any]] = []
    for filter_string in filters:
        try:
            batch = query_retail_prices(filter_string, max_records=400)
        except Exception:
            batch = []
        if batch:
            candidates.extend(batch)

    if not candidates:
        return None

    filtered = []
    for item in candidates:
        if normalize_text(item.get("type", "")) != "Consumption":
            continue
        meter_name = normalize_text(item.get("meterName", "")).lower()
        product_name = normalize_text(item.get("productName", "")).lower()
        uom = normalize_text(item.get("unitOfMeasure", "")).lower()
        if "data stored" not in meter_name:
            continue
        if "disk" in meter_name or "managed disk" in product_name or "mount" in meter_name:
            continue
        if "gb" not in uom:
            continue
        filtered.append(item)

    if not filtered:
        return None

    def rank(item: Dict[str, Any]) -> Tuple[int, datetime, float]:
        meter_name = normalize_text(item.get("meterName", "")).upper()
        red_score = 0
        if redundancy and redundancy in meter_name:
            red_score = 2
        elif not redundancy and "LRS" in meter_name:
            red_score = 1
        return (
            red_score + (1 if bool(item.get("isPrimaryMeterRegion", False)) else 0),
            parse_effective_date(item),
            maybe_float(item.get("retailPrice", 0.0), 0.0),
        )

    filtered.sort(key=rank, reverse=True)
    best = filtered[0]
    return PriceMatch(item=best, confidence=100, reason=normalize_text(best.get("meterName", "")))


def resolve_public_ip_price(sku: str, region: str, allow_devtest: bool = False) -> Optional[PriceMatch]:
    normalized_region = normalize_region(region)
    sku_text = normalize_text(sku) or "Standard"
    filters = [
        f"serviceName eq 'Virtual Network' and armRegionName eq '{normalized_region}' and contains(meterName,'Static') and contains(meterName,'Public IP')",
        f"serviceName eq 'Virtual Network' and armRegionName eq '{normalized_region}' and contains(meterName,'Static Public IP')",
        f"serviceName eq 'Virtual Network' and armRegionName eq '{normalized_region}' and contains(productName,'IP Addresses')",
    ]

    candidates: List[Dict[str, Any]] = []
    for filter_string in filters:
        try:
            batch = query_retail_prices(filter_string, max_records=400)
        except Exception:
            batch = []
        if batch:
            candidates.extend(batch)

    if not candidates:
        return None

    filtered = []
    for item in candidates:
        price_type = normalize_text(item.get("type", ""))
        if price_type not in {"Consumption", "DevTestConsumption"}:
            continue
        if not allow_devtest and price_type == "DevTestConsumption":
            continue
        meter_name = normalize_text(item.get("meterName", "")).lower()
        product_name = normalize_text(item.get("productName", "")).lower()
        item_sku = normalize_text(item.get("skuName", ""))
        if "public ip prefix" in product_name:
            continue
        if "static" not in meter_name:
            continue
        if "public ip" not in meter_name and "ip addresses" not in product_name:
            continue
        if sku_text and sku_text.lower() not in item_sku.lower():
            continue
        filtered.append(item)

    if not filtered:
        return None

    filtered.sort(
        key=lambda item: (
            bool(item.get("isPrimaryMeterRegion", False)),
            parse_effective_date(item),
            -maybe_float(item.get("retailPrice", 0.0), 0.0),
        ),
        reverse=True,
    )
    best = filtered[0]
    return PriceMatch(item=best, confidence=100, reason=normalize_text(best.get("meterName", "")))


def evaluate_input_quality(entry: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    resource = normalize_text(entry.get("Resource", ""))
    assumptions: List[str] = []
    gaps: List[str] = []

    if resource == "Virtual Machine":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing VM size SKU")
        if not normalize_text(entry.get("OS", "")):
            assumptions.append(f"OS defaulted to {runtime_option('default_vm_os', 'Linux')}")
    elif resource == "Managed Disk":
        if not normalize_text(entry.get("SKU", entry.get("Disk Type", ""))):
            gaps.append("Missing disk SKU/type")
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            assumptions.append("Disk size defaulted to 128 GB for family SKU")
    elif resource == "Storage Account":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing storage SKU")
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            assumptions.append("Storage size not provided; using 1 GB-equivalent baseline")
    elif resource == "Public IP":
        if not normalize_text(entry.get("SKU", "")):
            assumptions.append("Public IP SKU defaulted to Standard")
    elif resource == "Log Analytics":
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            assumptions.append("Log ingestion not provided; using baseline quantity")

    if maybe_int(entry.get("Hours", MONTHLY_HOURS_DEFAULT), MONTHLY_HOURS_DEFAULT) <= 0:
        gaps.append("Hours must be > 0")

    if not normalize_text(entry.get("Region", "")):
        assumptions.append("Region inferred from pricing mode/selection")

    return assumptions, gaps


def blocking_input_gaps(entry: Dict[str, Any]) -> List[str]:
    resource = normalize_text(entry.get("Resource", ""))
    gaps: List[str] = []

    if maybe_int(entry.get("Hours", MONTHLY_HOURS_DEFAULT), MONTHLY_HOURS_DEFAULT) <= 0:
        gaps.append("Hours must be > 0")

    if not normalize_text(entry.get("Region", "")):
        gaps.append("Missing Region")

    if resource == "Virtual Machine":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing VM size SKU")
        if not normalize_text(entry.get("OS", "")):
            gaps.append("Missing VM OS")
    elif resource == "Managed Disk":
        if not normalize_text(entry.get("SKU", entry.get("Disk Type", ""))):
            gaps.append("Missing disk SKU/type")
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            gaps.append("Missing disk size GB")
    elif resource == "Storage Account":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing storage SKU")
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            gaps.append("Missing storage size GB")
    elif resource == "SQL Database":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing SQL SKU")
    elif resource == "App Service":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing App Service SKU")
    elif resource == "Public IP":
        if not normalize_text(entry.get("SKU", "")):
            gaps.append("Missing Public IP SKU")
    elif resource == "Log Analytics":
        if maybe_float(entry.get("Disk Size GB", 0), 0) <= 0:
            gaps.append("Missing Log ingestion GB")
    elif resource == "Application Insights":
        assumptions.append("Application Insights cost excluded from totals by default")

    return gaps


def collect_blocking_issues(resources_df: pd.DataFrame) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for idx, row in resources_df.iterrows():
        row_dict = row.to_dict()
        gaps = blocking_input_gaps(row_dict)
        if gaps:
            issues.append(
                {
                    "Row": idx,
                    "Resource": normalize_text(row_dict.get("Resource", "")),
                    "SKU": normalize_text(row_dict.get("SKU", "")),
                    "Gaps": gaps,
                }
            )
    return issues


def apply_step6_input_prompts(resources_df: pd.DataFrame, selected_regions: List[str]) -> pd.DataFrame:
    if resources_df.empty:
        return resources_df

    updated = resources_df.copy()
    issues = collect_blocking_issues(updated)
    if not issues:
        st.success("All required pricing dimensions are present.")
        return updated

    st.warning(f"{len(issues)} row(s) need required fields before pricing.")
    with st.expander("Complete Required Inputs", expanded=True):
        region_options = []
        for name in DEFAULT_REGIONS + (selected_regions or []):
            normalized = normalize_region(name)
            if normalized and normalized not in region_options:
                region_options.append(normalized)
        if not region_options:
            region_options = ["eastus", "centralindia", "uksouth", "westus2"]

        for issue in issues:
            idx = issue["Row"]
            resource = issue["Resource"]
            gaps = issue["Gaps"]
            row = updated.loc[idx]
            st.markdown(f"Row {idx} - {resource} ({issue['SKU'] or 'No SKU'})")

            if "Missing Region" in gaps:
                current_region = normalize_region(row.get("Region", ""))
                default_region = current_region if current_region in region_options else region_options[0]
                region_value = st.selectbox(
                    "Region",
                    options=region_options,
                    index=region_options.index(default_region),
                    key=f"step6_region_{idx}",
                )
                updated.at[idx, "Region"] = region_value

            if "Missing VM size SKU" in gaps:
                vm_sku = st.text_input("VM size SKU", value=normalize_text(row.get("SKU", "")), key=f"step6_vm_sku_{idx}")
                updated.at[idx, "SKU"] = vm_sku

            if "Missing VM OS" in gaps:
                vm_os = st.selectbox("VM OS", options=["Windows", "Linux"], key=f"step6_vm_os_{idx}")
                updated.at[idx, "OS"] = vm_os

            if "Missing disk SKU/type" in gaps:
                disk_sku = st.text_input(
                    "Disk SKU/type",
                    value=normalize_text(row.get("SKU", "")) or normalize_text(row.get("Disk Type", "")),
                    key=f"step6_disk_sku_{idx}",
                )
                updated.at[idx, "SKU"] = disk_sku
                updated.at[idx, "Disk Type"] = disk_sku

            if "Missing disk size GB" in gaps:
                disk_size = st.number_input("Disk size GB", min_value=1.0, value=128.0, step=1.0, key=f"step6_disk_size_{idx}")
                updated.at[idx, "Disk Size GB"] = float(disk_size)

            if "Missing storage SKU" in gaps:
                storage_sku = st.text_input("Storage SKU", value=normalize_text(row.get("SKU", "")) or "Standard_LRS", key=f"step6_storage_sku_{idx}")
                updated.at[idx, "SKU"] = storage_sku

            if "Missing storage size GB" in gaps:
                storage_size = st.number_input("Storage size GB", min_value=1.0, value=1024.0, step=1.0, key=f"step6_storage_size_{idx}")
                updated.at[idx, "Disk Size GB"] = float(storage_size)

            if "Missing SQL SKU" in gaps:
                sql_sku = st.text_input("SQL SKU", value=normalize_text(row.get("SKU", "")), key=f"step6_sql_sku_{idx}")
                updated.at[idx, "SKU"] = sql_sku

            if "Missing App Service SKU" in gaps:
                app_sku = st.text_input("App Service SKU", value=normalize_text(row.get("SKU", "")), key=f"step6_app_sku_{idx}")
                updated.at[idx, "SKU"] = app_sku

            if "Missing Public IP SKU" in gaps:
                pip_sku = st.selectbox("Public IP SKU", options=["Standard", "Basic"], index=0, key=f"step6_pip_sku_{idx}")
                updated.at[idx, "SKU"] = pip_sku

            if "Missing Log ingestion GB" in gaps:
                log_gb = st.number_input("Log ingestion GB (monthly)", min_value=1.0, value=100.0, step=1.0, key=f"step6_log_gb_{idx}")
                updated.at[idx, "Disk Size GB"] = float(log_gb)

            if "Hours must be > 0" in gaps:
                hours = st.number_input("Hours", min_value=1, value=MONTHLY_HOURS_DEFAULT, step=1, key=f"step6_hours_{idx}")
                updated.at[idx, "Hours"] = int(hours)

            st.markdown("---")

    return updated


def infer_vm_os(properties: Dict[str, Any], current: str = "") -> str:
    direct = normalize_os(current)
    if direct:
        return direct

    os_disk_type = normalize_os(properties.get("storageProfile", {}).get("osDisk", {}).get("osType", ""))
    if os_disk_type:
        return os_disk_type

    image_ref = properties.get("storageProfile", {}).get("imageReference", {}) or {}
    hints = " ".join(
        [
            normalize_text(image_ref.get("publisher", "")).lower(),
            normalize_text(image_ref.get("offer", "")).lower(),
            normalize_text(image_ref.get("sku", "")).lower(),
        ]
    )
    if "windows" in hints or "microsoftwindows" in hints:
        return "Windows"
    if any(token in hints for token in ["ubuntu", "debian", "centos", "redhat", "suse", "linux"]):
        return "Linux"

    os_profile = properties.get("osProfile", {}) or {}
    if os_profile.get("windowsConfiguration"):
        return "Windows"
    if os_profile.get("linuxConfiguration"):
        return "Linux"
    return ""


def infer_excel_os(row: pd.Series) -> str:
    explicit = normalize_os(row.get("os", ""))
    if explicit:
        return explicit
    text = " ".join(
        [
            normalize_text(row.get("sku", "")).lower(),
            normalize_text(row.get("notes", "")).lower(),
            normalize_text(row.get("resourceType", "")).lower(),
        ]
    )
    if "windows" in text:
        return "Windows"
    if "linux" in text or "ubuntu" in text or "redhat" in text:
        return "Linux"
    return ""


def extract_template_parameters(payload: Dict[str, Any]) -> Dict[str, Any]:
    parameters = payload.get("parameters", {}) or {}
    result: Dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, dict) and "value" in value:
            result[key] = value.get("value")
        else:
            result[key] = value
    return result


def resolve_template_reference(expr: str, parameters: Dict[str, Any], variables: Dict[str, Any]) -> Any:
    text = normalize_text(expr)
    param_match = re.match(r"^\[\s*parameters\('([^']+)'\)\s*\]$", text, flags=re.IGNORECASE)
    if param_match:
        return parameters.get(param_match.group(1), expr)
    var_match = re.match(r"^\[\s*variables\('([^']+)'\)\s*\]$", text, flags=re.IGNORECASE)
    if var_match:
        return variables.get(var_match.group(1), expr)
    return expr


def resolve_template_value(value: Any, parameters: Dict[str, Any], variables: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: resolve_template_value(v, parameters, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_template_value(v, parameters, variables) for v in value]
    if isinstance(value, str):
        resolved = resolve_template_reference(value, parameters, variables)
        if resolved is value:
            return value
        return resolve_template_value(resolved, parameters, variables)
    return value


def extract_managed_disk_lookup(resources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for resource in resources:
        resource_type_text = normalize_text(resource.get("type", "")).lower()
        if "microsoft.compute/disks" not in resource_type_text and not resource_type_text.endswith("/disks"):
            continue
        name = normalize_text(resource.get("name", ""))
        rid = normalize_text(resource.get("id", ""))
        sku_name = normalize_text((resource.get("sku") or {}).get("name", ""))
        properties = resource.get("properties", {}) or {}
        disk_type = normalize_disk_sku(sku_name or properties.get("sku", {}).get("name", ""))
        disk_size = maybe_float(properties.get("diskSizeGB", 0), 0.0)
        data = {"disk_type": disk_type, "disk_size": disk_size}
        if name:
            lookup[name.lower()] = data
            lookup[name.split("/")[-1].lower()] = data
        if rid:
            lookup[rid.lower()] = data
            lookup[rid.split("/")[-1].lower()] = data
    return lookup


def lookup_disk_info(disk_ref: Any, disk_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(disk_ref, dict):
        return {}
    key_candidates = [
        normalize_text(disk_ref.get("id", "")).lower(),
        normalize_text(disk_ref.get("name", "")).lower(),
    ]
    for key in key_candidates:
        if key and key in disk_lookup:
            return disk_lookup[key]
        if key and key.split("/")[-1] in disk_lookup:
            return disk_lookup[key.split("/")[-1]]
    return {}


def select_preferred_item_by_uom(items: List[Dict[str, Any]], service: str) -> Dict[str, Any]:
    def uom_score(item: Dict[str, Any]) -> int:
        uom = normalize_text(item.get("unitOfMeasure", "")).lower()
        score = 0
        if service == "Virtual Machine":
            if "hour" in uom:
                score += 100
            if "month" in uom:
                score -= 20
        elif service in {
            "App Service",
            "Application Gateway",
            "Azure Firewall",
            "Public IP",
            "Load Balancer",
            "Log Analytics",
        }:
            if "month" in uom:
                score += 100
            if "hour" in uom:
                score -= 50
        elif service in {"Managed Disk", "Storage Account", "SQL Database"}:
            if "gb" in uom or "gib" in uom or "month" in uom:
                score += 100
            if "hour" in uom:
                score -= 50
        else:
            if "month" in uom or "gb" in uom or "gib" in uom:
                score += 50
        return score

    return max(items, key=uom_score)


def normalize_price_string(value: str) -> str:
    normalized = normalize_text(value).lower()
    normalized = re.sub(r"[\s_\-]+", "", normalized)
    normalized = re.sub(r"[^a-z0-9]", "", normalized)
    return normalized


def find_exact_price_candidate(
    items: List[Dict[str, Any]],
    sku: str,
    service: str,
    meter_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    sku_norm = normalize_price_string(sku)
    exact_items = []
    for item in items:
        if not sku_norm:
            continue
        if normalize_price_string(item.get("skuName", "")) == sku_norm:
            exact_items.append(item)
            continue
        if normalize_price_string(item.get("productName", "")) == sku_norm:
            exact_items.append(item)
            continue
        if normalize_price_string(item.get("meterName", "")) == sku_norm:
            exact_items.append(item)
            continue
    if exact_items:
        if meter_hint:
            hint_items = [
                item
                for item in exact_items
                if meter_hint.lower() in normalize_text(item.get("meterName", "")).lower()
                or meter_hint.lower() in normalize_text(item.get("productName", "")).lower()
            ]
            if hint_items:
                return select_preferred_item_by_uom(hint_items, service)
        return select_preferred_item_by_uom(exact_items, service)
    return None


def compute_monthly_units(item: Dict[str, Any], quantity: int, hours: int, gb_size: float) -> float:
    price = maybe_float(item.get("retailPrice", 0.0), 0.0)
    uom = normalize_text(item.get("unitOfMeasure", "")).lower()

    if re.search(r"(per\s*hour|/\s*hour|hour|hr)\b", uom):
        return price * hours * quantity

    if re.search(r"(gb|gib).*(/|per).*month|month.*(gb|gib)|gb.*month|gib.*month", uom):
        if gb_size <= 0:
            return price * quantity
        return price * gb_size * quantity

    if "month" in uom:
        return price * quantity

    if "gb" in uom or "gib" in uom:
        if gb_size <= 0:
            return price * quantity
        return price * gb_size * quantity

    return price * quantity


def build_odata_filter(filters: Dict[str, str]) -> str:
    clauses = []
    for field, value in filters.items():
        if not value:
            continue
        clauses.append(f"{field} eq '{value}'")
    return " and ".join(clauses)


def best_price_match(
    items: List[Dict[str, Any]],
    sku: str,
    region: str,
    meter_hint: Optional[str] = None,
) -> Optional[PriceMatch]:
    if not items:
        return None
    best = None
    best_score = -1
    for item in items:
        sku_score = max(
            fuzz.token_sort_ratio(sku, normalize_text(item.get("skuName", ""))),
            fuzz.token_sort_ratio(sku, normalize_text(item.get("productName", ""))),
            fuzz.token_sort_ratio(sku, normalize_text(item.get("meterName", ""))),
        )
        region_score = fuzz.token_sort_ratio(region, normalize_text(item.get("armRegionName", "")))
        meter_name = normalize_text(item.get("meterName", "")).lower()
        product_name = normalize_text(item.get("productName", "")).lower()
        uom = normalize_text(item.get("unitOfMeasure", "")).lower()
        hint_score = 0
        if meter_hint:
            if meter_hint.lower() in meter_name or meter_hint.lower() in product_name:
                hint_score = 100
        score = sku_score * 0.7 + region_score * 0.2 + hint_score * 0.1
        if "month" in uom or "gb" in uom or "gib" in uom:
            score += 20
        if "hour" in uom:
            score -= 30
        if "disk mount" in meter_name or "disk mount" in product_name:
            score += 20
        if "managed disks" in product_name:
            score += 10
        if "operations" in meter_name or "operations" in product_name:
            score -= 20
        if maybe_float(item.get("retailPrice", 0.0), 0.0) <= 0:
            score -= 15
        if score > best_score:
            best_score = score
            best = item
    if not best:
        return None
    confidence = int(min(100, max(30, best_score)))
    return PriceMatch(item=best, confidence=confidence, reason=best.get("meterName", ""))


def search_prices(service: str, sku: str, region: str, meter_hint: Optional[str] = None) -> Optional[PriceMatch]:
    if not service or not region:
        return None
    normalized_region = normalize_region(region)
    service_name = SERVICE_FILTERS.get(service, service)
    sku_text = normalize_text(sku)
    exact_queries: List[str] = []
    fallback_queries: List[str] = []

    if sku_text:
        exact_queries.append(build_odata_filter({"serviceName": service_name, "armRegionName": normalized_region, "skuName": sku_text}))
        if service == "App Service":
            app_service_sku = normalize_app_service_sku(sku_text)
            if app_service_sku and app_service_sku != sku_text:
                exact_queries.append(build_odata_filter({"serviceName": service_name, "armRegionName": normalized_region, "skuName": app_service_sku}))
        if service == "SQL Database":
            sql_sku = normalize_sql_sku(sku_text)
            if sql_sku and sql_sku != sku_text:
                exact_queries.append(build_odata_filter({"serviceName": service_name, "armRegionName": normalized_region, "skuName": sql_sku}))
        if service == "Managed Disk" and re.match(r"^[PSE]\d+\s?(LRS|ZRS)?$", sku_text, flags=re.IGNORECASE):
            exact_queries.append(build_odata_filter({"serviceName": service_name, "armRegionName": normalized_region, "skuName": sku_text}))

    for filter_string in exact_queries:
        if not filter_string:
            continue
        try:
            candidates = query_retail_prices(filter_string)
        except Exception:
            candidates = []
        if candidates:
            candidates = [
                item
                for item in candidates
                if normalize_text(item.get("type", "")) in {"Consumption", "DevTestConsumption"}
            ]
            if not bool(runtime_option("allow_devtest", False)):
                candidates = [item for item in candidates if normalize_text(item.get("type", "")) != "DevTestConsumption"]
        if not candidates:
            continue
        exact_item = find_exact_price_candidate(candidates, sku_text, service, meter_hint)
        if exact_item:
            return PriceMatch(item=exact_item, confidence=100, reason=exact_item.get("meterName", ""))

    if STRICT_PRICING_MATCH and service not in STRICT_FALLBACK_SERVICES:
        return None

    if sku_text:
        fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(skuName,'{sku_text}')")
        fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(productName,'{sku_text}')")
        fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(meterName,'{sku_text}')")
        if service == "Managed Disk":
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(meterName,'Disk')")
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(productName,'Managed Disks')")
        if service == "Public IP":
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(meterName,'Public IP')")
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(productName,'IP Addresses')")
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(meterName,'IP Address')")
        if service == "Log Analytics":
            fallback_queries.append(f"serviceName eq '{service_name}' and armRegionName eq '{normalized_region}' and contains(meterName,'Data Ingestion')")
    fallback_queries.append(build_odata_filter({"serviceName": service_name, "armRegionName": normalized_region}))

    for filter_string in fallback_queries:
        if not filter_string:
            continue
        try:
            candidates = query_retail_prices(filter_string)
        except Exception:
            candidates = []
        if candidates:
            candidates = [
                item
                for item in candidates
                if normalize_text(item.get("type", "")) in {"Consumption", "DevTestConsumption"}
            ]
            if not bool(runtime_option("allow_devtest", False)):
                candidates = [item for item in candidates if normalize_text(item.get("type", "")) != "DevTestConsumption"]
        if candidates:
            best_item = find_exact_price_candidate(candidates, sku_text, service, meter_hint)
            if best_item:
                return PriceMatch(item=best_item, confidence=100, reason=best_item.get("meterName", ""))
            return best_price_match(candidates, sku_text, region, meter_hint)

    return None


def parse_excel_file(uploaded_file: io.BytesIO) -> pd.DataFrame:
    with pd.ExcelFile(uploaded_file) as xls:
        df = pd.read_excel(xls, sheet_name=0)
    df = df.rename(columns={col: COLUMN_ALIASES.get(col.strip().lower(), col) for col in df.columns})
    extracted = []
    for _, row in df.iterrows():
        extracted.append({
            "Resource": standardize_resource_type(row.get("resourceType", "")),
            "SKU": normalize_text(row.get("sku", "")),
            "Region": normalize_region(row.get("region", "")),
            "Quantity": maybe_int(row.get("quantity", 1), 1),
            "Disk Type": normalize_text(row.get("diskType", "")),
            "Disk Size GB": maybe_float(row.get("diskSize", 0), 0.0),
            "OS": infer_excel_os(row),
            "Tier": normalize_text(row.get("tier", "")),
            "Hours": maybe_int(row.get("hours", MONTHLY_HOURS_DEFAULT), MONTHLY_HOURS_DEFAULT),
            "Notes": normalize_text(row.get("notes", "")),
        })
    return pd.DataFrame(extracted)


def parse_arm_template(content: str) -> pd.DataFrame:
    payload = json.loads(content)

    if isinstance(payload, dict):
        parameters = extract_template_parameters(payload)
        variables_raw = payload.get("variables", {}) or {}
        variables = resolve_template_value(variables_raw, parameters, variables_raw)
        payload = resolve_template_value(payload, parameters, variables)

    resources = []

    def collect_resources(resource_list):
        for resource in resource_list:
            resources.append(resource)
            nested_resources = resource.get("resources")
            if isinstance(nested_resources, list):
                collect_resources(nested_resources)

    if isinstance(payload, dict):
        collect_resources(payload.get("resources", []) or [])
    elif isinstance(payload, list):
        collect_resources(payload)

    disk_lookup = extract_managed_disk_lookup(resources)

    extracted = []
    for resource in resources:
        normalized = normalize_arm_resource(resource, disk_lookup=disk_lookup)
        if isinstance(normalized, list):
            extracted.extend(normalized)
        else:
            extracted.append(normalized)
    if not extracted:
        st.warning("No resources found in ARM template. Please verify the JSON format.")
    return pd.DataFrame(extracted)


def normalize_arm_resource(resource: Dict[str, Any], disk_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    disk_lookup = disk_lookup or {}
    properties = resource.get("properties", {}) or {}
    sku_data = resource.get("sku") or {}
    resource_type_text = normalize_text(resource.get("type", ""))
    resource_type = standardize_resource_type(resource_type_text)
    sku_name = normalize_text(sku_data.get("name", "")) or normalize_text(sku_data.get("tier", ""))
    location = normalize_region(resource.get("location", ""))
    tier = normalize_text(sku_data.get("tier", "")) or normalize_text(properties.get("tier", ""))

    if resource_type == "Unknown" and "/" in resource_type_text:
        fallback = resource_type_text.split("/")[-1]
        resource_type = re.sub(r"([a-z])([A-Z])", r"\1 \2", fallback).replace("-", " ").title()

    row = {
        "Resource": resource_type,
        "SKU": sku_name,
        "Region": location,
        "Quantity": 1,
        "Disk Type": "",
        "Disk Size GB": 0.0,
        "OS": "",
        "Tier": tier,
        "Hours": MONTHLY_HOURS_DEFAULT,
        "Notes": "ARM template source",
    }

    if "virtualmachines" in resource_type_text.lower() or "microsoft.compute/virtualmachines" in resource_type_text.lower():
        vm_size = normalize_text(properties.get("hardwareProfile", {}).get("vmSize", ""))
        row["SKU"] = normalize_vm_sku(vm_size) or row["SKU"]
        os_type = normalize_text(properties.get("storageProfile", {}).get("osDisk", {}).get("osType", ""))
        row["OS"] = infer_vm_os(properties, os_type)

        disk_rows = []
        os_disk = properties.get("storageProfile", {}).get("osDisk", {}) or {}
        os_disk_ref = os_disk.get("managedDisk", {}) or {}
        resolved_os_disk = lookup_disk_info(os_disk_ref, disk_lookup)
        os_disk_type = normalize_disk_sku(os_disk_ref.get("storageAccountType", "")) or normalize_text(resolved_os_disk.get("disk_type", ""))
        os_disk_size = maybe_float(os_disk.get("diskSizeGB", 0), 0.0) or maybe_float(resolved_os_disk.get("disk_size", 0), 0.0)
        if os_disk_type:
            disk_rows.append(
                {
                    "Resource": "Managed Disk",
                    "SKU": os_disk_type,
                    "Region": location,
                    "Quantity": 1,
                    "Disk Type": os_disk_type,
                    "Disk Size GB": os_disk_size,
                    "OS": "",
                    "Tier": "",
                    "Hours": MONTHLY_HOURS_DEFAULT,
                    "Notes": "ARM template source - OS disk",
                }
            )

        data_disks = properties.get("storageProfile", {}).get("dataDisks", []) or []
        for disk in data_disks:
            disk_ref = disk.get("managedDisk", {}) or {}
            resolved_data_disk = lookup_disk_info(disk_ref, disk_lookup)
            disk_size = maybe_float(disk.get("diskSizeGB", 0), 0.0) or maybe_float(resolved_data_disk.get("disk_size", 0), 0.0)
            disk_name = (
                normalize_disk_sku(disk.get("sku", {}).get("name", ""))
                or normalize_disk_sku(disk_ref.get("storageAccountType", ""))
                or normalize_text(resolved_data_disk.get("disk_type", ""))
            )
            if disk_name:
                disk_rows.append(
                    {
                        "Resource": "Managed Disk",
                        "SKU": disk_name,
                        "Region": location,
                        "Quantity": 1,
                        "Disk Type": disk_name,
                        "Disk Size GB": disk_size,
                        "OS": "",
                        "Tier": "",
                        "Hours": MONTHLY_HOURS_DEFAULT,
                        "Notes": "ARM template source - data disk",
                    }
                )

        row["Disk Type"] = ""
        row["Disk Size GB"] = 0.0
        if disk_rows:
            return [row] + disk_rows
    elif "microsoft.compute/disks" in resource_type_text.lower() or "disks" in resource_type_text.lower():
        row["Disk Type"] = normalize_disk_sku(sku_name)
        row["Disk Size GB"] = maybe_float(properties.get("diskSizeGB", 0), 0.0)
        row["SKU"] = row["Disk Type"]
    elif "storageaccounts" in resource_type_text.lower() or "microsoft.storage/storageaccounts" in resource_type_text.lower():
        row["SKU"] = normalize_text((resource.get("sku") or {}).get("name", "")) or row["SKU"]
        row["Tier"] = normalize_text(resource.get("kind", "")) or row["Tier"]
    elif "sqlservers/databases" in resource_type_text.lower() or (
        "databases" in resource_type_text.lower() and "sql" in resource_type_text.lower()
    ):
        row["SKU"] = normalize_text(properties.get("requestedServiceObjectiveName", "")) or row["SKU"]
        row["Tier"] = normalize_text(properties.get("sku", {}).get("tier", "")) or row["Tier"]
    elif "web/sites" in resource_type_text.lower() or "microsoft.web/sites" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or row["SKU"]
        row["Resource"] = "App Service"
    elif "applicationgateways" in resource_type_text.lower() or "microsoft.network/applicationgateways" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or "Application Gateway"
        row["Resource"] = "Application Gateway"
    elif "microsoft.network/publicipaddresses" in resource_type_text.lower() or "publicipaddresses" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or "Public IP"
        row["Resource"] = "Public IP"
    elif "microsoft.network/loadbalancers" in resource_type_text.lower() or "loadbalancers" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or "Load Balancer"
        row["Resource"] = "Load Balancer"
    elif "microsoft.network/azurefirewalls" in resource_type_text.lower() or "azurefirewalls" in resource_type_text.lower():
        row["Resource"] = "Azure Firewall"
    elif "microsoft.operationalinsights/workspaces" in resource_type_text.lower() or "workspaces" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or "Log Analytics"
        row["Resource"] = "Log Analytics"
    elif "microsoft.insights/components" in resource_type_text.lower() or "components" in resource_type_text.lower():
        row["SKU"] = normalize_text(sku_name) or "Application Insights"
        row["Resource"] = "Application Insights"
    elif "networkinterfaces" in resource_type_text.lower() or "microsoft.network/networkinterfaces" in resource_type_text.lower():
        row["Resource"] = "Network Interface"
    elif "virtualnetworks" in resource_type_text.lower() or "microsoft.network/virtualnetworks" in resource_type_text.lower():
        row["Resource"] = "Virtual Network"
    elif "networksecuritygroups" in resource_type_text.lower() or "microsoft.network/networksecuritygroups" in resource_type_text.lower():
        row["Resource"] = "Network Security Group"
    if row.get("SplitDiskPricing"):
        disk_row = {
            "Resource": "Managed Disk",
            "SKU": normalize_disk_sku(row.get("Disk Type", "")) or row.get("Disk Type", ""),
            "Region": row.get("Region", ""),
            "Quantity": 1,
            "Disk Type": row.get("Disk Type", ""),
            "Disk Size GB": row.get("Disk Size GB", 0.0),
            "OS": "",
            "Tier": "",
            "Hours": row.get("Hours", MONTHLY_HOURS_DEFAULT),
            "Notes": "ARM template source - Managed Disk details",
            "SplitDiskPricing": False,
        }
        return [row, disk_row]
    return row


def parse_screenshot_image(uploaded_file: io.BytesIO) -> pd.DataFrame:
    if easyocr is None:
        st.warning("EasyOCR is not installed. Screenshot parsing requires easyocr.")
        return pd.DataFrame([])
    reader = easyocr.Reader(["en"], gpu=False)
    image_bytes = uploaded_file.read()
    image = image_bytes
    raw_results = reader.readtext(image, detail=1, paragraph=False)
    lines_by_row = {}
    for box, text, prob in raw_results:
        y = int(sum([pt[1] for pt in box]) / 4)
        lines_by_row.setdefault(y, []).append((box, text))
    rows = []
    for y in sorted(lines_by_row.keys()):
        text_parts = [text for _, text in sorted(lines_by_row[y], key=lambda x: x[0][0][0])]
        rows.append(" ".join(text_parts))
    header = []
    data = []
    for row in rows:
        normalized = row.lower()
        if any(key in normalized for key in ["resource", "sku", "region", "quantity"]):
            header = [col.strip() for col in re.split(r"\s{2,}|\s*,\s*|\|", row) if col.strip()]
            continue
        if header and row.strip():
            values = [val.strip() for val in re.split(r"\s{2,}|\s*,\s*|\|", row) if val.strip()]
            if len(values) == len(header):
                data.append(values)
    if not header or not data:
        st.warning("Unable to parse screenshot table automatically. Please try a cleaner screenshot or use Excel/ARM input.")
        return pd.DataFrame([])
    normalized_rows = []
    for values in data:
        if len(values) < len(header):
            values = values + [""] * (len(header) - len(values))
        elif len(values) > len(header):
            values = values[: len(header) - 1] + [" ".join(values[len(header) - 1 :])]
        normalized_rows.append(values)
    df = pd.DataFrame(normalized_rows, columns=header)
    df = df.rename(columns={col: COLUMN_ALIASES.get(col.strip().lower(), col) for col in df.columns})
    output = io.BytesIO()
    df.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    return parse_excel_file(output)


def price_vm(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    sku = normalize_vm_sku(entry.get("SKU", ""))
    os_type = normalize_os(entry.get("OS", "")) or normalize_os(runtime_option("default_vm_os", "Linux"))
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    hours = maybe_int(entry.get("Hours", MONTHLY_HOURS_DEFAULT), MONTHLY_HOURS_DEFAULT)
    disk_type = normalize_disk_sku(entry.get("Disk Type", ""))
    disk_size = maybe_float(entry.get("Disk Size GB", 0), 0.0)

    compute_match = resolve_vm_price(
        sku,
        region,
        os_type,
        allow_spot=bool(runtime_option("allow_spot", False)),
        allow_devtest=bool(runtime_option("allow_devtest", False)),
    )
    compute_cost = 0.0
    compute_conf = 0
    compute_reason = ""
    if compute_match:
        compute_cost = compute_monthly_units(compute_match.item, quantity, hours, 0)
        compute_conf = compute_match.confidence
        compute_reason = compute_match.reason

    disk_cost = 0.0
    disk_conf = 0
    disk_reason = ""
    if not entry.get("SplitDiskPricing") and disk_size > 0 and disk_type:
        disk_norm = normalize_disk_sku(disk_type)
        disk_match = search_prices("Managed Disk", disk_norm, region)
        if disk_match:
            disk_cost = compute_monthly_units(disk_match.item, quantity, hours, disk_size)
            disk_conf = disk_match.confidence
            disk_reason = disk_match.reason
    total = compute_cost + disk_cost
    confidence = int(min(100, max(compute_conf, disk_conf or 0)))
    reason = ", ".join(filter(None, [compute_reason, disk_reason]))
    return total, confidence, reason or "Virtual Machine pricing"


def price_managed_disk(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    disk_type = normalize_disk_sku(entry.get("SKU", entry.get("Disk Type", "")))
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    size_gb = maybe_float(entry.get("Disk Size GB", 0), 0)

    # ARM VM OS disks often omit explicit size; use a practical default so we can
    # map family SKUs (Premium/Standard SSD/HDD) to a concrete disk tier.
    if size_gb <= 0 and not re.match(r"^[PSE]\d+", disk_type, flags=re.IGNORECASE):
        disk_text = disk_type.lower()
        if "premium" in disk_text or "standard ssd" in disk_text or "standard hdd" in disk_text:
            size_gb = 128

    tier_sku = disk_tier_from_size(disk_type, size_gb)
    query_sku = tier_sku or disk_type
    if disk_type.lower().startswith("p") and size_gb <= 0:
        size_gb = 128
    disk_match = resolve_managed_disk_price(query_sku, region)
    if not disk_match and query_sku != disk_type:
        disk_match = resolve_managed_disk_price(disk_type, region)
    if not disk_match:
        disk_match = search_prices("Managed Disk", query_sku, region, meter_hint="Disk")
    if not disk_match:
        return 0.0, 0, ""
    price = compute_monthly_units(disk_match.item, quantity, MONTHLY_HOURS_DEFAULT, size_gb)
    return price, disk_match.confidence, disk_match.reason


def price_storage_account(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    sku = normalize_text(entry.get("SKU", ""))
    tier = normalize_text(entry.get("Tier", ""))
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    size_gb = maybe_float(entry.get("Disk Size GB", 0), 0)
    match = resolve_storage_account_price(sku, tier, region)
    if not match and tier:
        match = search_prices("Storage Account", tier, region)
    if not match and sku:
        match = search_prices("Storage Account", sku, region)
    if not match:
        return 0.0, 0, ""
    price = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, size_gb)
    return price, match.confidence, match.reason


def price_sql_database(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    sku = normalize_text(entry.get("SKU", ""))
    tier = normalize_text(entry.get("Tier", ""))
    size_gb = maybe_float(entry.get("Disk Size GB", 0), 0)
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    match = None
    if sku:
        match = search_prices("SQL Database", sku, region)
        if not match:
            fallback_sku = normalize_sql_sku(sku)
            if fallback_sku and fallback_sku != sku:
                match = search_prices("SQL Database", fallback_sku, region)
    if not match and tier:
        match = search_prices("SQL Database", tier, region)
    base = 0.0
    confidence = 0
    reason = ""
    if match:
        base = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, 0)
        confidence = match.confidence
        reason = match.reason
    storage_cost = 0.0
    if size_gb > 0:
        storage_match = search_prices("SQL Database", "storage", region)
        if storage_match:
            storage_cost = compute_monthly_units(storage_match.item, quantity, MONTHLY_HOURS_DEFAULT, size_gb)
            if not confidence:
                confidence = storage_match.confidence
            if not reason:
                reason = storage_match.reason
    total = base + storage_cost
    return total, confidence, reason


def price_app_service(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    raw_sku = normalize_text(entry.get("SKU", ""))
    sku = normalize_app_service_sku(raw_sku) or raw_sku
    if not sku:
        return 0.0, 0, ""
    match = search_prices("App Service", sku, region)
    if not match and raw_sku != sku:
        match = search_prices("App Service", raw_sku, region)
    if not match:
        return 0.0, 0, ""
    price = compute_monthly_units(match.item, maybe_int(entry.get("Quantity", 1), 1), MONTHLY_HOURS_DEFAULT, 0)
    return price, match.confidence, match.reason


def price_application_gateway(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    sku = normalize_text(entry.get("SKU", "")) or "Application Gateway"
    match = search_prices("Application Gateway", sku, region)
    if not match:
        return 0.0, 0, ""
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    price = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, 0)
    return price, match.confidence, match.reason


def price_firewall(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    match = search_prices("Azure Firewall", "Firewall", region)
    if not match:
        return 0.0, 0, ""
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    price = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, 0)
    return price, match.confidence, match.reason


def price_public_ip(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    sku = normalize_text(entry.get("SKU", "")) or "Standard"
    match = resolve_public_ip_price(sku, region, allow_devtest=bool(runtime_option("allow_devtest", False)))
    if not match:
        match = search_prices("Public IP", sku, region, meter_hint="Public IP")
    if not match:
        match = search_prices("Public IP", "IP Address", region, meter_hint="IP Address")
    if not match:
        return 0.0, 0, ""
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    price = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, 0)
    return price, match.confidence, match.reason


def price_load_balancer(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    match = search_prices("Load Balancer", "Load Balancer", region)
    if not match:
        return 0.0, 0, ""
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    price = compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, 0)
    return price, match.confidence, match.reason


def price_log_analytics(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    size_gb = maybe_float(entry.get("Disk Size GB", 0), 0)
    quantity = maybe_int(entry.get("Quantity", 1), 1)
    match = search_prices("Log Analytics", "Data Ingestion", region, meter_hint="Data Ingestion")
    if not match:
        return 0.0, 0, ""
    return compute_monthly_units(match.item, quantity, MONTHLY_HOURS_DEFAULT, size_gb), match.confidence, match.reason


def price_application_insights(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    # Monitoring intentionally excluded from hard-resource totals for accuracy focus.
    return 0.0, 100, "Monitoring pricing deferred"


def price_virtual_network(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    return 0.0, 100, "No direct base charge (usage-dependent networking)"


def price_network_interface(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    return 0.0, 100, "No direct base charge (usage-dependent networking)"


def price_network_security_group(entry: Dict[str, Any], region: str) -> Tuple[float, int, str]:
    return 0.0, 100, "No direct base charge (usage-dependent networking)"


def auto_enrich_resources(resources_df: pd.DataFrame, selected_regions: List[str], pricing_mode: str) -> pd.DataFrame:
    if resources_df.empty:
        return resources_df

    enriched = resources_df.copy()
    selected_norm = [normalize_region(r) for r in selected_regions if normalize_region(r)]
    existing_regions = [normalize_region(v) for v in enriched.get("Region", pd.Series([], dtype=str)).tolist() if normalize_region(v)]
    fallback_region = selected_norm[0] if selected_norm else (existing_regions[0] if existing_regions else "eastus")

    for idx, row in enriched.iterrows():
        resource = normalize_text(row.get("Resource", ""))
        notes = normalize_text(row.get("Notes", ""))

        region = normalize_region(row.get("Region", ""))
        if not region:
            region = fallback_region if pricing_mode == "Use resource region from input" else fallback_region
            enriched.at[idx, "Region"] = region
            notes = f"{notes}; auto: Region={region}" if notes else f"auto: Region={region}"

        hours = maybe_int(row.get("Hours", MONTHLY_HOURS_DEFAULT), MONTHLY_HOURS_DEFAULT)
        if hours <= 0:
            enriched.at[idx, "Hours"] = MONTHLY_HOURS_DEFAULT
            notes = f"{notes}; auto: Hours=730" if notes else "auto: Hours=730"

        if resource == "Virtual Machine":
            os_type = normalize_os(row.get("OS", ""))
            if not os_type:
                os_type = normalize_os(runtime_option("default_vm_os", "Linux"))
                enriched.at[idx, "OS"] = os_type
                notes = f"{notes}; auto: OS={os_type}" if notes else f"auto: OS={os_type}"

        if resource == "Public IP":
            sku = normalize_text(row.get("SKU", ""))
            if not sku:
                enriched.at[idx, "SKU"] = "Standard"
                notes = f"{notes}; auto: PublicIP SKU=Standard" if notes else "auto: PublicIP SKU=Standard"

        if resource == "Managed Disk":
            disk_type = normalize_text(row.get("SKU", "")) or normalize_text(row.get("Disk Type", ""))
            if disk_type and not normalize_text(row.get("Disk Type", "")):
                enriched.at[idx, "Disk Type"] = disk_type
            size = maybe_float(row.get("Disk Size GB", 0), 0)
            if size <= 0 and any(x in disk_type.lower() for x in ["premium", "standard ssd", "standard hdd"]):
                enriched.at[idx, "Disk Size GB"] = 128.0
                notes = f"{notes}; auto: DiskSizeGB=128" if notes else "auto: DiskSizeGB=128"

        if resource == "Storage Account":
            sku = normalize_text(row.get("SKU", ""))
            if not sku:
                enriched.at[idx, "SKU"] = "Standard_LRS"
                notes = f"{notes}; auto: Storage SKU=Standard_LRS" if notes else "auto: Storage SKU=Standard_LRS"

        if resource == "Log Analytics":
            size = maybe_float(row.get("Disk Size GB", 0), 0)
            if size <= 0:
                enriched.at[idx, "Disk Size GB"] = 100.0
                notes = f"{notes}; auto: LogIngestionGB=100" if notes else "auto: LogIngestionGB=100"

        enriched.at[idx, "Notes"] = notes

    return enriched


PRICING_FUNCTIONS = {
    "Virtual Machine": price_vm,
    "Managed Disk": price_managed_disk,
    "Storage Account": price_storage_account,
    "SQL Database": price_sql_database,
    "App Service": price_app_service,
    "Application Gateway": price_application_gateway,
    "Azure Firewall": price_firewall,
    "Public IP": price_public_ip,
    "Load Balancer": price_load_balancer,
    "Log Analytics": price_log_analytics,
    "Application Insights": price_application_insights,
    "Virtual Network": price_virtual_network,
    "Network Interface": price_network_interface,
    "Network Security Group": price_network_security_group,
}


def price_resources(resources: pd.DataFrame, regions: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    rows = []
    region_totals = []
    requested_regions = [normalize_region(r) for r in regions if normalize_region(r)]
    region_mode = bool(requested_regions)

    loop_regions = requested_regions if requested_regions else ["input-resource-region"]
    strict_mode = bool(runtime_option("strict_input_validation", False))
    for region in loop_regions:
        total_region = 0.0
        for _, entry in resources.iterrows():
            resource_region = normalize_region(entry.get("Region", ""))
            price_region = region if region_mode else (resource_region or region)
            resource_type = entry.get("Resource", "Unknown")
            assumptions, gaps = evaluate_input_quality(entry)
            pricing_fn = PRICING_FUNCTIONS.get(resource_type)
            include_in_total = True
            if strict_mode and gaps:
                cost, confidence, meter = 0.0, 0, "Missing required inputs"
            elif pricing_fn:
                cost, confidence, meter = pricing_fn(entry, price_region)
            else:
                cost, confidence, meter = 0.0, 0, "Unsupported"

            if resource_type in MONITORING_RESOURCES:
                include_in_total = False
                assumptions.append("Excluded from hard-resource total")

            if gaps and not strict_mode:
                confidence = min(confidence, 70)

            rows.append(
                {
                    "Resource": resource_type,
                    "SKU": entry.get("SKU", ""),
                    "Region": price_region,
                    "Quantity": entry.get("Quantity", 1),
                    "Hours": entry.get("Hours", MONTHLY_HOURS_DEFAULT),
                    "Azure Pricing Calculator Equivalent Monthly Price": round(cost, 4),
                    "Confidence %": confidence,
                    "Pricing Source Meter": meter,
                    "Included In Total": include_in_total,
                    "Assumptions": " | ".join(assumptions),
                    "Input Gaps": " | ".join(gaps),
                    "Notes": entry.get("Notes", ""),
                }
            )
            if include_in_total:
                total_region += cost
        region_totals.append({"Region": region, "Total Monthly Price": round(total_region, 4)})
    result_df = pd.DataFrame(rows)
    region_df = pd.DataFrame(region_totals)
    cheapest = region_df.loc[region_df["Total Monthly Price"].idxmin()]["Region"] if not region_df.empty else "N/A"
    summary = f"Cheapest region (hard resources): {cheapest}."
    return result_df, region_df, summary


def download_excel(dataframes: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dataframes.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def main() -> None:
    st.set_page_config(page_title="Azure Pricing Calculator Automation", layout="wide")
    st.title("Azure Pricing Calculator Automation")
    st.markdown(
        "A Streamlit tool to ingest Azure Excel, screenshots, or ARM templates and estimate monthly costs using the Azure Retail Prices API."
    )

    st.sidebar.header("Input Source")
    input_mode = st.sidebar.radio(
        "Choose upload method",
        ["Excel file", "Screenshot", "ARM JSON upload", "ARM JSON paste"],
    )
    selected_regions = st.sidebar.multiselect(
        "Select regions for comparison",
        options=DEFAULT_REGIONS,
        default=DEFAULT_REGIONS[:2],
    )
    custom_region = st.sidebar.text_input("Add custom region", value="")
    if custom_region:
        selected_regions.append(custom_region.strip())

    pricing_mode = st.sidebar.radio(
        "Pricing mode",
        ["Compare selected regions", "Use resource region from input"],
        index=0,
    )
    st.sidebar.subheader("VM pricing assumptions")
    default_vm_os = st.sidebar.selectbox("Default VM OS when missing", ["Linux", "Windows"], index=0)
    allow_spot = st.sidebar.checkbox("Allow Spot/Low Priority meters", value=False)
    allow_devtest = st.sidebar.checkbox("Allow Dev/Test meters", value=False)
    strict_input_validation = st.sidebar.checkbox("Strict input completeness (skip rows with missing required fields)", value=False)

    RUNTIME_PRICING_OPTIONS["default_vm_os"] = default_vm_os
    RUNTIME_PRICING_OPTIONS["allow_spot"] = allow_spot
    RUNTIME_PRICING_OPTIONS["allow_devtest"] = allow_devtest
    RUNTIME_PRICING_OPTIONS["strict_input_validation"] = strict_input_validation

    if not selected_regions:
        st.sidebar.warning("Select at least one region")

    if "resources_df" not in st.session_state or st.session_state.get("input_mode") != input_mode:
        st.session_state["resources_df"] = pd.DataFrame([])
        st.session_state["resource_source"] = ""
        st.session_state["input_mode"] = input_mode

    resources_df = st.session_state["resources_df"]
    resource_source = st.session_state["resource_source"]

    uploaded = None
    arm_text = ""
    if input_mode == "Excel file":
        uploaded = st.file_uploader("Upload Azure resources Excel", type=["xlsx", "xls"])
    elif input_mode == "Screenshot":
        uploaded = st.file_uploader("Upload screenshot of Excel sheet", type=["png", "jpg", "jpeg"])
    elif input_mode == "ARM JSON upload":
        uploaded = st.file_uploader("Upload ARM template JSON", type=["json"])
    else:
        arm_text = st.text_area("Paste ARM template JSON")

    extract_clicked = st.button("Extract Azure resources")
    if extract_clicked:
        if input_mode == "Excel file" and uploaded:
            try:
                resources_df = parse_excel_file(uploaded)
                resource_source = "Excel"
            except Exception as err:
                st.error(f"Could not parse Excel file: {err}")
                resources_df = pd.DataFrame([])
        elif input_mode == "Screenshot" and uploaded:
            try:
                resources_df = parse_screenshot_image(uploaded)
                resource_source = "Screenshot"
            except Exception as err:
                st.error(f"Screenshot parsing failed: {err}")
                resources_df = pd.DataFrame([])
        elif input_mode == "ARM JSON upload" and uploaded:
            try:
                resources_df = parse_arm_template(uploaded.getvalue().decode("utf-8"))
                resource_source = "ARM JSON"
            except Exception as err:
                st.error(f"Could not parse ARM template: {err}")
                resources_df = pd.DataFrame([])
        elif input_mode == "ARM JSON paste" and arm_text:
            try:
                resources_df = parse_arm_template(arm_text)
                resource_source = "ARM JSON Paste"
            except Exception as err:
                st.error(f"Could not parse ARM template text: {err}")
                resources_df = pd.DataFrame([])
        else:
            st.warning("Please provide input before extracting resources.")
            resources_df = pd.DataFrame([])

        st.session_state["resources_df"] = resources_df
        st.session_state["resource_source"] = resource_source

    if resources_df.empty:
        st.info("Upload/paste data and click 'Extract Azure resources' to parse resources.")
        return

    st.subheader("Extracted Azure Resources")
    if hasattr(st, "experimental_data_editor"):
        editable_df = st.experimental_data_editor(resources_df, num_rows="dynamic")
    elif hasattr(st, "data_editor"):
        editable_df = st.data_editor(resources_df, num_rows="dynamic")
    else:
        st.warning("Editable table not available in this Streamlit version. Showing read-only output.")
        st.dataframe(resources_df)
        editable_df = resources_df

    editable_df = auto_enrich_resources(editable_df, selected_regions, pricing_mode)
    st.session_state["resources_df"] = editable_df

    blocking_issues = collect_blocking_issues(editable_df)
    if blocking_issues:
        st.warning("Some fields were auto-filled using defaults. Review Notes/Assumptions in results.")

    can_generate = True
    has_pricing_scope = bool(selected_regions) or pricing_mode == "Use resource region from input"

    if has_pricing_scope and not editable_df.empty:
        if st.button("Generate Pricing", disabled=not can_generate):
            with st.spinner("Calculating pricing from Azure Retail Prices API..."):
                pricing_regions = selected_regions if pricing_mode == "Compare selected regions" else []
                result_df, region_df, summary = price_resources(editable_df, pricing_regions)
            st.subheader("Pricing Results")
            st.dataframe(result_df)
            st.markdown(f"**{summary}**")
            st.markdown("### Region comparison")
            st.dataframe(region_df)
            file_bytes = download_excel({"Pricing": result_df, "Summary": region_df})
            st.download_button(
                "Export results to Excel",
                data=file_bytes,
                file_name="azure_pricing_calculator_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Built for Azure Pricing Calculator alignment using `serviceName`, `skuName`, `productName`, `meterName`, and `armRegionName` from Azure Retail Prices API."
    )


if __name__ == "__main__":
    main()
