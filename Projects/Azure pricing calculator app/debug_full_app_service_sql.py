import app

print('App Service direct')
entry={'Resource':'App Service','SKU':'P1v2','Region':'uksouth','Quantity':1,'Disk Size GB':0.0,'Tier':'PremiumV2','Hours':730,'Notes':'ARM template source'}
res = app.price_app_service(entry,'uksouth')
print(res)

print('SQL direct')
entry2={'Resource':'SQL Database','SKU':'GP_Gen5_2','Region':'centralindia','Quantity':1,'Disk Size GB':0.0,'Tier':'GeneralPurpose','Hours':730,'Notes':'ARM template source'}
res2 = app.price_sql_database(entry2,'centralindia')
print(res2)
print('search 36 vCore', app.search_prices('SQL Database','36 vCore','centralindia'))
print('search P1 v2', app.search_prices('App Service','P1 v2','uksouth'))
