import pandas as pd
from sqlalchemy import create_engine
from config_loader import get_config

# Создайте соединение с вашей базой данных PostgreSQL
engine = create_engine('postgresql://postgres:12345@localhost:5433/postgres')

config = get_config()


# Загрузите данные из CSV
contracts = pd.read_excel(config.get("WRITE_TABLE", "contracts"))
tenders = pd.read_excel(config.get("WRITE_TABLE", "tenders"))
procurement = pd.read_excel(config.get("WRITE_TABLE", "procurement"))

# Загрузите данные в PostgreSQL
contracts.to_sql('contracts', engine, if_exists='replace', index=False)
tenders.to_sql('tenders', engine, if_exists='replace', index=False)
procurement.to_sql('procurement', engine, if_exists='replace', index=False)