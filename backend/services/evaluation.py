from services.comparation import TenderMatcher
from services.extraction import extraction
from config_loader import get_config
import os
import pandas as pd

def evaluate():
    config = get_config()
    matcher = TenderMatcher(db_url='postgresql://postgres:12345@localhost:5433/postgres')
    tenders_df, procurement_df = matcher.load_data()
    true_answers = pd.read_excel(config.get("EVALUTION", "true_answers"))
    root_dir = config.get("EVALUTION", "root_dir")

    for file_path in os.listdir(config.get("EVALUTION", "root_dir")):
        full_file_path = os.path.join(root_dir, file_path)
        # file_path = "C:\\Users\\mi\\Documents\\Diplom_Ali4i4\\messages\\FW PR №OF0000014401 Контрагент Химмед ТД ООО требует согласования - dipl.msg"
        user_data = extraction(full_file_path)  # Предположим, что extraction() возвращает данные пользователя
        try:
            processed_user_data = matcher.process_user_data(user_data)
        except:
            continue
        procurement_codes = matcher.find_procurement_code(processed_user_data, procurement_df)
        similar_tenders = matcher.find_similar_tenders(processed_user_data, tenders_df, procurement_codes)
        # После получения similar_tenders:
        all_suppliers = set()
        for tender in similar_tenders:
            all_suppliers.update(tender['участники'])
        all_suppliers_str = ",".join(all_suppliers)
        true_answers.loc[true_answers['message'] == file_path.split('.')[0], 'model_answer'] = all_suppliers_str

        # metrics = true_answers.apply(lambda row: calculate_metrics(row["True_answer"], row["model_answer"]), axis=1)
        # print (metrics)
    return true_answers

# Функция для расчета метрик
def calculate_metrics(true, pred):
    # Преобразуем списки в множества
    true_set = set(true)
    if not pd.isna(pred):
        pred_set = set(pred)
    else:
        return 0, 0, 0, 0, 0
    
    # Рассчитываем метрики
    precision = len(true_set.intersection(pred_set)) / len(pred_set) if len(pred_set) > 0 else 0
    recall = len(true_set.intersection(pred_set)) / len(true_set) if len(true_set) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    exact_match = 1 if true_set == pred_set else 0
    jaccard = len(true_set.intersection(pred_set)) / len(true_set.union(pred_set)) if len(true_set.union(pred_set)) > 0 else 0
    
    return precision, recall, f1, exact_match, jaccard



if __name__ == "__main__":
    df = evaluate()
    metrics = df.apply(lambda row: calculate_metrics(row["True_answer"], row["model_answer"]), axis=1)
    # Создаем DataFrame с результатами
    metrics_df = pd.DataFrame(metrics.tolist(), columns=["Precision", "Recall", "F1-Score", "Exact Match", "Jaccard"])

    # Добавляем метрики к исходной таблице
    result_df = pd.concat([df, metrics_df], axis=1)

    # Выводим результат
    print(result_df)

    # Средние метрики
    print("\nСредние метрики:")
    print(metrics_df.mean())
    result_df.to_csv("resulst.csv")
