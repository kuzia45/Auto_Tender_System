import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import re
from services.extraction import extraction
from services.contacts_matcher import CompanyContactMatcher
from sqlalchemy import create_engine
from config_loader import get_config

class TenderMatcher:
    def __init__(
        self,
        db_url,
        model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        weights=None,
        top_n=3,
    ):
        self.model_name = model_name
        self.engine = create_engine(db_url)
        self.weights = weights if weights else {"items_text": 0.8, "suppliers": 0.2}
        self.top_n = top_n
        self.model = SentenceTransformer(self.model_name)

    def load_data(self):
        tenders_df = pd.read_sql('SELECT * FROM tenders', self.engine)
        procurement_df = pd.read_sql('SELECT * FROM procurement', self.engine)
        # Обработка участников с удалением спецсимволов
        tenders_df["участники"] = tenders_df["участники"].apply(
            lambda x: list(set(
                re.sub(r'[^\w\s]', '', s.strip())  # Удаляем спецсимволы
                for s in str(x).split(";")         # Разделяем по ";"
            )) if pd.notna(x) else []
        )

        tenders_df["Items_clean"] = tenders_df["Items"].apply(
            lambda x: re.sub(r"\s+", " ", str(x))
        )  # Удаляем лишние пробелы

        return tenders_df, procurement_df

    def process_user_data(self, user_data):
        items_text = (
            " ".join(user_data["Тендер"]["Товары/услуги"])
            if user_data.get("Тендер").get("Товары/услуги")
            else ""
        )
        suppliers = set(user_data.get("Тендер").get("Возможные_поставщики", []))

        return {"items_text": items_text, "suppliers": suppliers}

    def find_procurement_code(self, user_data, procurement_df):
        descriptions = procurement_df["Description"].tolist()
        keywords = procurement_df["Key-words"].tolist()
        all_texts = [user_data["items_text"]] + descriptions + keywords
        all_texts = [str(x) for x in all_texts if str(x) != "nan"]

        text_embeddings = self.model.encode(all_texts, show_progress_bar=True)
        user_text_vec = text_embeddings[0].reshape(1, -1)
        db_text_vecs = text_embeddings[1:]

        similarities = cosine_similarity(user_text_vec, db_text_vecs)[0]

        description_similarities = similarities[1 : len(descriptions) + 1]
        keyword_similarities = similarities[len(descriptions) + 1 :]

        procurement_codes = set()

        max_description_index = np.argmax(description_similarities)
        max_description_value = description_similarities[max_description_index]

        max_keyword_index = np.argmax(keyword_similarities)
        max_keyword_value = keyword_similarities[max_keyword_index]

        if max_description_value > 0.5:
            procurement_codes.add(
                procurement_df.iloc[max_description_index]["NEW HACAT Code"]
            )
        if max_keyword_value > 0.5:
            procurement_codes.add(
                procurement_df.iloc[max_keyword_index]["NEW HACAT Code"]
            )

        return procurement_codes

    def find_similar_tenders(self, user_data, tenders_df, procurement_codes):
        filtered_tenders = tenders_df[tenders_df["Commodity"].isin(procurement_codes)].copy()
    
        if filtered_tenders.empty:
            filtered_tenders = tenders_df.copy()
    
        # Преобразуем участников в списки
        filtered_tenders["участники"] = filtered_tenders["участники"].apply(
            lambda x: x if isinstance(x, list) else []
        )

        db_texts = filtered_tenders["Items_clean"].tolist()
        all_texts = [user_data["items_text"]] + db_texts

        text_embeddings = self.model.encode(all_texts, show_progress_bar=False)
        user_text_vec = text_embeddings[0].reshape(1, -1)
        db_text_vecs = text_embeddings[1:]

        text_sim = cosine_similarity(user_text_vec, db_text_vecs)[0]

        supplier_sim = []
        for db_suppliers in filtered_tenders["участники"].apply(
            lambda x: set(str(x).split("; "))
        ):
            intersection = len(user_data["suppliers"] & db_suppliers)
            union = len(user_data["suppliers"] | db_suppliers)
            supplier_sim.append(intersection / union if union != 0 else 0)

        combined_sim = self.weights["items_text"] * text_sim + self.weights[
            "suppliers"
        ] * np.array(supplier_sim)

        top_indices = np.argsort(combined_sim)[-self.top_n :][::-1]
        results = filtered_tenders.iloc[top_indices][
            ["Event #", "Commodity", "участники", "Items_clean"]
        ]

        return results.to_dict('records')


# Пример использования
if __name__ == "__main__":
    config = get_config()
    matcher = TenderMatcher(db_url='postgresql://postgres:12345@localhost:5433/postgres')
    tenders_df, procurement_df = matcher.load_data()
    file_path = config.get("COMPARATION", "file_path")
    user_data = extraction(file_path)  # Предположим, что extraction() возвращает данные пользователя
    # kp = extraction("C:\\Users\\mi\\Documents\\Diplom_Ali4i4\\pdf_data\\2.pdf")
    processed_user_data = matcher.process_user_data(user_data)
    procurement_codes = matcher.find_procurement_code(processed_user_data, procurement_df)
    similar_tenders = matcher.find_similar_tenders(processed_user_data, tenders_df, procurement_codes)
    # После получения similar_tenders:
    all_suppliers = set()
    for tender in similar_tenders:
        all_suppliers.update(tender['участники'])
    print(all_suppliers)
    
    contacts_matcher = CompanyContactMatcher(
        threshold=20,
        synonyms=None
    )
    # Загрузка контактов
    contacts_matcher.load_contacts()
    results = contacts_matcher.find_contacts(all_suppliers)
    
    print (results)
