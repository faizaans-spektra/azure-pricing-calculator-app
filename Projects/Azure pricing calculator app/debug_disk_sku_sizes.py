import requests
api = 'https://prices.azure.com/api/retail/prices'
regions = ['eastus', 'uksouth', 'centralindia', 'westus2']
skus = ['P1 LRS', 'P2 LRS', 'P3 LRS', 'P4 LRS', 'P6 LRS', 'P10 LRS', 'P15 LRS', 'P20 LRS', 'P30 LRS', 'P40 LRS', 'P50 LRS', 'E4 LRS', 'E6 LRS', 'E10 LRS', 'E15 LRS', 'E20 LRS', 'E30 LRS', 'E40 LRS', 'S4 LRS', 'S6 LRS', 'S10 LRS', 'S15 LRS', 'S20 LRS', 'S30 LRS', 'S40 LRS']
for region in regions:
    print('REGION', region)
    for sku in skus:
        try:
            f = f"serviceName eq 'Storage' and armRegionName eq '{region}' and skuName eq '{sku}' and contains(meterName,'Disk')"
            r = requests.get(api, params={'$filter': f}, timeout=30)
            data = r.json()
            if data.get('Count', 0) > 0:
                item = data['Items'][0]
                print(sku, item.get('meterName'), item.get('productName'), item.get('unitOfMeasure'), item.get('retailPrice'))
        except Exception as ex:
            print('ERR', sku, ex)
    print()
