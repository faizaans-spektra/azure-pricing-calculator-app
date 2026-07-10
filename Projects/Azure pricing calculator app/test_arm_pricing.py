import json
import app

samples = [
    {
        "description": "VM with managed disk and nested resources",
        "template": {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "resources": [
                {
                    "type": "Microsoft.Compute/virtualMachines",
                    "apiVersion": "2024-04-01",
                    "name": "vm1",
                    "location": "East US 2",
                    "properties": {
                        "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
                        "storageProfile": {
                            "osDisk": {
                                "managedDisk": {"storageAccountType": "Premium_LRS"},
                                "osType": "Windows"
                            },
                            "dataDisks": [
                                {"diskSizeGB": 128, "sku": {"name": "Premium_LRS"}},
                                {"diskSizeGB": 256, "sku": {"name": "StandardSSD_LRS"}}
                            ]
                        }
                    }
                },
                {
                    "type": "Microsoft.Storage/storageAccounts",
                    "apiVersion": "2024-06-01",
                    "name": "stg1",
                    "location": "East US",
                    "sku": {"name": "Standard_LRS"},
                    "kind": "StorageV2",
                    "properties": {}
                }
            ]
        }
    },
    {
        "description": "SQL database resource",
        "template": {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "resources": [
                {
                    "type": "Microsoft.Sql/servers/databases",
                    "apiVersion": "2024-02-01-preview",
                    "name": "sqlserver1/db1",
                    "location": "Central India",
                    "sku": {"name": "GP_Gen5_2", "tier": "GeneralPurpose"},
                    "properties": {"requestedServiceObjectiveName": "GP_Gen5_2"}
                }
            ]
        }
    },
    {
        "description": "App Service with app service plan SKU",
        "template": {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "resources": [
                {
                    "type": "Microsoft.Web/sites",
                    "apiVersion": "2024-04-01",
                    "name": "webapp1",
                    "location": "UK South",
                    "sku": {"name": "P1v2", "tier": "PremiumV2"},
                    "properties": {}
                }
            ]
        }
    },
    {
        "description": "Nested child resources example",
        "template": {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "resources": [
                {
                    "type": "Microsoft.Network/virtualNetworks",
                    "apiVersion": "2024-05-01",
                    "name": "vnet1",
                    "location": "West US 2",
                    "properties": {},
                    "resources": [
                        {
                            "type": "Microsoft.Network/networkSecurityGroups",
                            "apiVersion": "2024-06-01",
                            "name": "nsg1",
                            "location": "West US 2",
                            "properties": {}
                        }
                    ]
                }
            ]
        }
    }
]

regions = ["eastus", "centralindia", "uksouth", "westus2"]

for sample in samples:
    print('---', sample['description'])
    resources_df = app.parse_arm_template(json.dumps(sample['template']))
    result_df, region_df, summary = app.price_resources(resources_df, regions)
    print('Parsed resources:')
    print(resources_df.to_string(index=False))
    print('\nPricing result:')
    print(result_df.to_string(index=False))
    print('\nRegion totals:')
    print(region_df.to_string(index=False))
    print('\nSummary:', summary)
    print('\n')
