import json
import os
from openai import OpenAI
from services.msg_parser import MsgParser
import json_repair
import re
from bs4 import BeautifulSoup
from services.pdf_parser import PDFToStringConverter
from config_loader import get_config

FEW_SHOT = """ПРИМЕР ИЗВЛЕЧЕНИЯ: \n\n {
    "Извлечение": {
        "schema": {
            "id": "Тендер",
            "description": "Необходимо извлечь сущности, которые необходимы для запуска тендера",
            "attributes": [
                {
                    "$type": "Text",
                    "id": "Товары/услуги",
                    "description": "Найди при начилии в ТЕКСТ товары или услуги для закупки. Их может быть несколько",
                    "many": true,
                    "value": ["Подача деклараций на товары (ДТ) с 1-3 кодами ТН ВЭД",
                    "Декларация соответствия на алл.колпачки",
                    "ЭЦП (электронная цифровая подпись)",
                    "Поддержка при подготовке к подаче ДТ, определение кода ТН ВЭД, отчёты для камеральной проверки, CMR",      
                    "Таможенное оформление (включая подготовку документов, сканирование договоров, УНК, описаний товаров)"
                    ]
                },
                {
                    "$type": "Text",
                    "id": "Бюджет",
                    "description": "Найди при наличии в ТЕКСТ бюджет закупки, т.е. ожидаемая сумма затрат для закупки",
                    "many": false,
                    "value": "870 000 рублей"
                },
                {
                    "$type": "Text",
                    "id": "Срок",
                    "description": "Найди при наличии в ТЕКСТ ожидаемую дату/срок получения товара или услуги после закупки. Если такой информации нет в ТЕКСТ, оставь поле пустым.",
                    "many": false,
                    "value": ""
                },
                {
                    "$type": "Text",
                    "id": "Бизнес_партнер",
                    "description": "Найди при наличии в ТЕКСТ бизнес-партнера. Бизнес-партнер этот тот, кто выдвигает требования к закупке. Это человек, а не компания. Обычно это отправитель одного из первых писем",
                    "many": true,
                    "value": ["Pakalo, Grigoriy /RU (Procurement Category & Efficiency Manager, Sanofi)", 
                    "Mysnik, Vladislav /RU (Customs and MMD manager, Sanofi)", "Popova, Alina /RU (сотрудник Sanofi)"]
                },
                {
                    "$type": "Text",
                    "id": "Возможные_поставщики",
                    "description": "Найди при наличии в ТЕКСТ возможных поставщиков, если они были упомянуты в переписке. Если их нет, оставь поле пустым.",
                    "many": true,
                    "value": ["ООО «Экспресс Брокер» (контакт: Тарасова Надежда Юрьевна, tn@rb57.ru, +74862543170)", 
                    "Вектор Лоджистик (контакт: Алон Амухвари, ab_rus@vector-logistics.ru, +74955102988)", 
                    "Руста Брокер (контакт: Ласкин Роман Викторович, irv@rusta-broker.ru, +84952695157)", 
                    "КОРЕКС (контакт: Maksim Zvezdarev, maxim.zvezdarev@corex-depot.com)"]
                }
            ]
        }
    }
}"""


class DeepSeekAPI:
    def __init__(self, api_key, base_url="https://openrouter.ai/api/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def call_api(
        self,
        system_prompt,
        user_prompt,
        model="microsoft/mai-ds-r1:free",
        temperature=0,
        max_tokens=1500,
        top_p=1,
    ):
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            top_p=top_p,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content


class DocumentProcessor:
    def __init__(self, system_prompt, msg_scheme_path, pdf_scheme_path):
        self.system_prompt = system_prompt
        self.file_type = None

        # Загружаем обе схемы
        with open(msg_scheme_path, "r", encoding="utf-8") as file:
            self.msg_scheme = json.load(file)

        with open(pdf_scheme_path, "r", encoding="utf-8") as file:
            self.pdf_scheme = json.load(file)

    def process_file(self, file_path):
        """Обработка файла с автоматическим определением типа"""
        self.file_type = os.path.splitext(file_path)[1].lower()

        if self.file_type == ".msg":
            return self._process_msg_file(file_path)
        elif self.file_type == ".pdf":
            return self._process_pdf_file(file_path)
        else:
            raise ValueError("Unsupported file format")

    def _process_msg_file(self, msg_file_path):
        """Обработка .msg файла"""
        with MsgParser(msg_file_path) as parser:
            parser.parse_msg()
            return parser.to_json()

    def _process_pdf_file(self, pdf_file_path):
        """Обработка PDF файла"""
        converter = PDFToStringConverter(pdf_file_path)
        return converter.convert_to_string() or ""

    def get_full_prompt(self, extracted_text):
        """Выбор схемы в зависимости от типа файла"""
        if self.file_type == ".msg":
            scheme = self.msg_scheme
        elif self.file_type == ".pdf":
            scheme = self.pdf_scheme
        else:
            scheme = {}

        return (
            self.system_prompt + "\nВот схема извлечения \n" + json.dumps(scheme, ensure_ascii=False) + FEW_SHOT,
            extracted_text,
        )


def process_result(raw_json_str):
    try:
        json_tagged = BeautifulSoup(raw_json_str, features="lxml").find_all("json")
        json_input = json_tagged[-1].text if json_tagged else raw_json_str
        json_input = re.sub(
            r"\b(True|False)\b",
            lambda x: x.group(0).lower(),
            re.sub(
                r"<json>|</json>",
                "",
                json_input.replace("null", "").replace("``", '""'),
            )
            .strip()
            .replace('" "', '","'),
        )
        result = json_repair.loads(json_input)

        # Встраиваем функцию extract_data
        def extract_data(element):
            def process_node(node):
                result = {}

                if "attributes" in node:
                    groups = {}
                    for attr in node["attributes"]:
                        if "attributes" in attr:  # Вложенная группа
                            processed = process_node(attr)
                            key = attr["id"]

                            if attr.get("many", False):
                                if key not in groups:
                                    groups[key] = []
                                groups[key].append(processed)
                            else:
                                groups[key] = processed
                        else:  # Конечное поле
                            result[attr["id"]] = attr.get("value", attr.get("values", ""))

                    result.update(groups)

                if "id" in node and "attributes" not in node:
                    return {node["id"]: node.get("value", attr.get("values", ""))}

                return result

            return {element["id"]: process_node(element)}

        # Применяем extract_data к результату
        if isinstance(result, dict) and "Извлечение" in result:
            try:
                return extract_data(result["Извлечение"]["schema"])
            except:
                try:
                    return extract_data(result["Извлечение"])
                except:
                    print("Неверная структура JSON")
                    return {}
        return result

    except Exception as e:
        print(f"Error processing JSON: {str(e)}")
        return []


def extraction(input_file):

    config = get_config()


    # Обновленные настройки
    api_key = (
        config.get("EXTRUCTION", "api_key")
)
    system_prompt = "Ты - специалист отдела закупок. Твоя задача - извлечь необходимую информацию из документа. Извлекать нужно по схеме, описанной ниже. Выводи извлечение в формате JSON\n\n"

    # Пути к схемам
    msg_scheme_path = config.get("EXTRUCTION", "msg_scheme_path")
    pdf_scheme_path = config.get("EXTRUCTION", "pdf_scheme_path")

    # # Путь к файлу (может быть .msg или .pdf)
    # input_file = (
    #     "C:\\Users\\mi\\Documents\\Diplom_Ali4i4\\messages\\FW Кейс №21171 поступил на согласование  Case #21171 is pending approval - dipl.msg"  # Пример с PDF
    # )

    # Инициализация
    deepseek_api = DeepSeekAPI(api_key)
    processor = DocumentProcessor(system_prompt, msg_scheme_path, pdf_scheme_path)

    try:
        # Обработка файла
        extracted_text = processor.process_file(input_file)

        # Формирование промта
        full_system_prompt, user_prompt = processor.get_full_prompt(extracted_text)

        # Вызов API
        result = deepseek_api.call_api(full_system_prompt, user_prompt)

        # Вывод результата
        if result:
            processed_data = process_result(result)
            print(
                "Processed Data:",
                json.dumps(processed_data, ensure_ascii=False, indent=2),
            )
            return processed_data
    except Exception as e:
        print(f"Ошибка обработки файла: {str(e)}")

