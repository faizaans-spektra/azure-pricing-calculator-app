import json
import app

sample = {
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
}

resources_df = app.parse_arm_template(json.dumps(sample['template']))
print('parsed')
print(resources_df.to_string(index=False))
result_df, region_df, summary = app.price_resources(resources_df, ['centralindia'])
print('result')
print(result_df.to_string(index=False))
print(region_df.to_string(index=False))
print(summary)
