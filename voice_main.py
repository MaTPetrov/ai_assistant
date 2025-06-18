import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
from PIL import Image, ImageTk, ImageSequence
import time
import ollama
import json
from pathlib import Path
import subprocess
import os
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
import queue


#открытие файла с данными пользователя
with open("personal_data.txt", "r") as file:
    global personal_data
    # Читаем содержимое файла
    personal_data = file.read()

# Цвета интерфейса
USER_TEXT_COLOR = "#00FA9A"  # Белый
AI_TEXT_COLOR = "#b180d7"    # Фиолетовый
BACKGROUND_COLOR = "#2c2f33"  # Тёмный фон

#--------------------------------------------------------------------------------------------------------------------------------------------------------


class HybridMemory:
    def __init__(self):
        self.current_dialog = []  # Текущая сессия (полные сообщения)
        self.summarized_history = ""  # Сжатая история прошлых сессий
        self.load_history()
        # Добавляем обработчик команд
        self.command_handlers = {
            "open_browser": self.open_browser,
            "open_explorer": self.open_explorer,
            "open_terminal": self.open_terminal,
            "shutdown": self.shutdown,
            "reboot": self.reboot,
            "open_path": self.open_path
        }

    def load_history(self):
        """Загружает суммаризированную историю из файла"""
        history_file = Path("summary.json")
        if history_file.exists():
            with open(history_file, 'r') as f:
                data = json.load(f)
                self.summarized_history = data.get("summary", "")

    def save_history(self):
        """Сохраняет сжатую историю при выключении"""
        summary = self.generate_summary()
        Path("memory").mkdir(exist_ok=True)

        with open("summary.json", 'w') as f:
            json.dump({
                "summary": summary,
                "last_update": time.strftime("%Y-%m-%d %H:%M")
            }, f)

    def generate_summary(self):
        """Генерирует сжатое описание всей истории"""
        if not self.current_dialog:
            return self.summarized_history

        prompt = f"""
        [Текущая сессия]
        {self.current_dialog[-20:]}  # Последние 20 реплик

        [Предыдущая история]
        {self.summarized_history}

        Создай подробную сводку (10-15 предложений), выделяя:
        - Основные темы обсуждения
        - Важные факты о пользователе
        - Ключевые решения/действия
        """
        response = ollama.generate(
            model="mistral",
            prompt=prompt,
            options={"temperature": 0.1}  # Для более фактологического стиля
        )
        return response

    def get_context(self):
        """Возвращает полный контекст для модели"""
        return f"""
        ### СЖАТАЯ ИСТОРИЯ ###
        {self.summarized_history}

        ### ТЕКУЩИЙ ДИАЛОГ (последние 10 сообщений) ###
        {self.current_dialog[-10:]}
        """

#--------------------------------------------------------------------------------------------------------------------------------------------------------
#голос




#--------------------------------------------------------------------------------------------------------------------------------------------------------

def check_ollama_connection(max_retries=5, delay=2):
    """Проверяет подключение к Ollama с повторными попытками"""
    for i in range(max_retries):
        try:
            ollama.list()
            print("✅ Успешное подключение к Ollama")
            return True
        except:
            print(f"⚠️ Попытка {i+1}/{max_retries}: не удалось подключиться к Ollama")
            time.sleep(delay)
    raise ConnectionError("Не удалось подключиться к Ollama после нескольких попыток")

# В начале __init__ класса AnimeAssistant добавьте:
#check_ollama_connection()

#--------------------------------------------------------------------------------------------------------------------------------------------------------


class AnimeAssistant:

    audio_token = True

    def __init__(self, root):
        self.root = root
        root.title("AI Assistant")
        root.geometry("880x600")
        root.configure(bg="#2c2f33")

        # Инициализация
        self.context = []
        self.model = "mistral"
        self.recording = False
        
        # Простая инициализация Vosk
        self.vosk_model = Model("model") if os.path.exists("model") else None
        if self.vosk_model:
            print("✅ Модель распознавания речи загружена")
        else:
            print("⚠️ Модель распознавания не найдена")

        # Создаем интерфейс
        self.setup_ui()

        # Инициализация модели
        self.init_model()

    def setup_ui(self):
        """Создание интерфейса"""
        # Стиль
        style = ttk.Style()
        style.configure("TFrame", background="#2c2f33")
        style.configure("TButton", background="#7289da", foreground="white")
        style.configure("TLabel", background="#2c2f33", foreground="white")
        style.configure("TEntry", fieldbackground="#40444b", foreground="white")
        style.configure("TScrollbar", background="#23272a")
        
        #style.configure("character_frame", background="#8A2BE2")

        # Основные фреймы
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Фрейм персонажа
        character_frame = ttk.Frame(main_frame, width=300)
        character_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Аниме-тянка (анимированный GIF)
        self.character_label = ttk.Label(character_frame)
        self.character_label.pack(pady=10)
        self.load_gif("character.gif", "default")  # Замените на свой GIF-файл

        # Статус персонажа
        self.status_label = ttk.Label(character_frame, text="Готова помочь!", font=("Arial", 12))
        self.status_label.pack(pady=5)

        # Фрейм чата
        chat_frame = ttk.Frame(main_frame)
        chat_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # История чата
        self.chat_history = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg="#36393f",
            fg="white",
            insertbackground="white",
            font=("Arial", 12),
            padx=10,
            pady=10
        )
        self.chat_history.pack(fill=tk.BOTH, expand=True)
        self.chat_history.config(state=tk.DISABLED)

        # Фрейм ввода
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, pady=(10, 0))

        # Кнопка микрофона
        self.mic_button = ttk.Button(
            input_frame,
            text="🎤",
            command=self.start_voice_input
        )
        self.mic_button.pack(side=tk.LEFT, padx=(0, 5))

        self.user_input = ttk.Entry(
            input_frame,
            font=("Arial", 12),
            width=50
        )
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.user_input.bind("<Return>", self.send_message)

        self.send_button = ttk.Button(
            input_frame,
            text="Отправить",
            command=self.send_message
        )
        self.send_button.pack(side=tk.RIGHT)

        # Приветственное сообщение
        self.add_to_chat("Мику", "Привет! Чем могу помочь?")

    # голоc
    def start_voice_input(self):
        """Запуск голосового ввода в отдельном потоке"""
        if not self.vosk_model:
            self.add_to_chat("Ошибка", "Модель распознавания не загружена")
            return
            
        self.mic_button.config(text="🔴")
        self.set_emotion("thinking")
        threading.Thread(target=self.record_and_send, daemon=True).start()

    def record_and_send(self):

        
        # Конфигурация
        MODEL_PATH = "model"  # Путь к модели Vosk
        SAMPLE_RATE = 16000   # Частота дискретизации

        # Инициализация модели
        model = Model(MODEL_PATH)
        recognizer = KaldiRecognizer(model, SAMPLE_RATE)
        recognizer.SetWords(False)

        # Очередь для аудиоданных
        audio_queue = queue.Queue()

        def audio_callback(indata, frames, time, status):
            """Обратный вызов для записи аудио"""
            audio_queue.put(bytes(indata))
        
        try:
            # Открываем аудиопоток
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=8000,
                dtype='int16',
                channels=1,
                callback=audio_callback
            ):
                while True:
                    # Получаем аудиоданные из очереди
                    data = audio_queue.get()
                    
                    # Обрабатываем аудио
                    if recognizer.AcceptWaveform(data):
                        result = recognizer.Result()
                        text = json.loads(result)["text"]
                        if text:
                            print(f"\nРаспознано: {text}")
                            if "пауза" in text:
                                self.audio_token = False

                            if "мику" in text:
                                # Вставляем текст в поле ввода
                                self.user_input.delete(0, tk.END)
                                self.user_input.insert(0, text)
                                self.send_message()
                                self.audio_token = True
                            elif self.audio_token:
                                self.user_input.delete(0, tk.END)
                                self.user_input.insert(0, text)
                                self.send_message()

                            
                            


        except Exception as e:
            print(f"Ошибка: {str(e)}")

# --------------------------------------------------------------------------------------------------------------------------------------------------------

    def load_gif(self, filename, emoticon):
        """Загрузка и отображение анимированного GIF"""
        try:
            #выбор от эмоции

            #default
            if emoticon == "default":
                self.gif = Image.open("emoticon/neutral.png")
                self.frames = [ImageTk.PhotoImage(frame.copy()) for frame in ImageSequence.Iterator(self.gif)]

            #thinking
            if emoticon == "thinking":
                self.gif = Image.open("emoticon/thinking.png")
                self.frames = [ImageTk.PhotoImage(frame.copy()) for frame in ImageSequence.Iterator(self.gif)]

            #happy
            if emoticon == "happy":
                self.gif = Image.open("emoticon/happy.png")
                self.frames = [ImageTk.PhotoImage(frame.copy()) for frame in ImageSequence.Iterator(self.gif)]
            self.frames = [ImageTk.PhotoImage(frame.copy()) for frame in ImageSequence.Iterator(self.gif)]
            self.frame_index = 0
            self.animate()
        except FileNotFoundError:
            # Заглушка если GIF не найден
            no_image = Image.new('RGB', (300, 400), color=(50, 50, 50))
            self.frames = [ImageTk.PhotoImage(no_image)]
            self.character_label.configure(image=self.frames[0])

    def animate(self):
        """Анимация персонажа"""
        if self.frames:
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.character_label.configure(image=self.frames[self.frame_index])
            self.root.after(100, self.animate)  # Скорость анимации

# --------------------------------------------------------------------------------------------------------------------------------------------------------

    def set_emotion(self, emotion):
        """Смена эмоции (для примера - просто меняем текст)"""
        self.current_emotion = emotion
        emotions_text = {
            "default": "Готова помочь!",
            "thinking": "Думаю...",
            "happy": "Рада помочь! ^_^"
        }
        self.status_label.config(text=emotions_text.get(emotion, "Готова помочь!"))
        self.load_gif("pass.png", emotion)



    def init_model(self):
        global personal_data
        """Проверка и загрузка модели"""
        threading.Thread(target=self.check_model, daemon=True).start()

        # Перенесем инициализацию модели в отдельный поток
        threading.Thread(target=self.initialize_context, args=(personal_data,), daemon=True).start()


    def initialize_context(self, personal_data):
        # 1. Добавляем сообщение пользователя в историю (не в ScrolledText!)
        self.context.append({"role": "user", "content": personal_data})

        # 2. Формируем контекст
        messages = [
            *self.context[-8:]  # Берём 8 последних сообщений
        ]

        # 3. Запрос к модели
        response = ollama.chat(
            model=self.model,
            messages=messages,
            stream=False
        )

        # 4. Сохраняем ответ
        ai_response = response['message']['content']
        self.context.append({"role": "assistant", "content": ai_response})

# --------------------------------------------------------------------------------------------------------------------------------------------------------

    def check_model(self):
        """Проверка доступности модели"""
        try:
            models = ollama.list()
            if not any(m['name'] == self.model for m in models['models']):
                self.add_to_chat("Система", f"Скачиваю модель {self.model}...")
                ollama.pull(self.model)
                self.add_to_chat("Система", "Модель готова к работе!")
        except Exception as e:
            pass
            #self.add_to_chat("Ошибка", f"Не удалось загрузить модель: {str(e)}")

# --------------------------------------------------------------------------------------------------------------------------------------------------------

    def add_to_chat(self, sender, message):
        """Добавление сообщения в чат"""
        self.chat_history.config(state=tk.NORMAL)
        if sender == "Мику":
            self.chat_history.tag_config("ai", foreground=AI_TEXT_COLOR)
            self.chat_history.insert(tk.END, f"{sender}: {message}\n\n", "ai")
        else:
            self.chat_history.tag_config("user", foreground=USER_TEXT_COLOR)
            self.chat_history.insert(tk.END, f"{sender}: {message}\n\n", "user")
        self.chat_history.config(state=tk.DISABLED)
        self.chat_history.see(tk.END)

    def send_message(self, event=None):
        """Отправка сообщения"""
        user_text = self.user_input.get().strip()
        if not user_text:
            return

        self.add_to_chat("Вы", user_text)
        self.user_input.delete(0, tk.END)
        self.set_emotion("thinking")

        # Запуск в отдельном потоке
        threading.Thread(target=self.get_ai_response, args=(user_text,), daemon=True).start()

# --------------------------------------------------------------------------------------------------------------------------------------------------------

    def get_ai_response(self, user_text):
        """Получение ответа от ИИ с полной очисткой JSON"""
        
        # Основные команды и их ключевые слова
        COMMAND_KEYWORDS = {
            "firefox": ["браузер", "firefox", "интернет", "веб"],
            "nautilus": ["файловый менеджер", "проводник", "файлы", "nautilus", "обзор файлов"],
            "kitty": ["терминал", "консоль", "командная строка"],
            "gedit": ["текстовый редактор", "gedit", "редактор текста", "заметки"],
        }
        
        # 1. Очистка контекста от старых JSON-ответов
        self.context = [msg for msg in self.context if not isinstance(msg.get('content', ''), str) or '{' not in msg['content']]
        
        # 2. Проверка на команды открытия
        user_text_lower = user_text.lower()
        
        # Расширенные триггеры команд
        open_triggers = ["открой", "запусти", "открыть", "запустить", "включи", 
                        "открый", "откроешь", "запустишь", "можешь открыть", "можно открыть"]
        
        # Проверяем наличие ключевых слов для каждого приложения
        for app_cmd, keywords in COMMAND_KEYWORDS.items():
            for keyword in keywords:
                # Если есть ключевое слово и любой из триггеров
                if (keyword in user_text_lower and 
                    any(trigger in user_text_lower for trigger in open_triggers)):
                    try:
                        subprocess.Popen(app_cmd, shell=True, start_new_session=True)
                        
                        # Красивые названия для ответа
                        app_names = {
                            "firefox": "браузер Firefox",
                            "nautilus": "файловый менеджер",
                            "kitty": "терминал kitty",
                            "gedit": "текстовый редактор"
                        }
                        
                        # Простой ответ без JSON
                        response_text = f"Открываю {app_names.get(app_cmd, app_cmd)}!"
                        self.add_to_chat("Мику", response_text)
                        
                        # Эмоции
                        self.set_emotion("happy")
                        self.root.after(2000, lambda: self.set_emotion("default"))
                        return
                    except Exception as e:
                        self.add_to_chat("Ошибка", f"Не удалось выполнить команду: {str(e)}")
                        self.set_emotion("default")
                        return
        
        # 3. Основной запрос к ИИ для обычных вопросов
        try:
            # Добавляем сообщение в контекст
            self.context.append({"role": "user", "content": user_text})
            
            # Формируем чистый контекст без системных промптов
            messages = [msg for msg in self.context[-8:] if not msg.get('content', '').startswith('{')]
            
            # Запрос к модели
            response = ollama.chat(
                model=self.model,
                messages=messages,
                stream=False
            )
            
            # Сохраняем ответ
            ai_response = response['message']['content']
            
            # Полная очистка ответа от JSON
            if isinstance(ai_response, str):
                ai_response = ai_response.split('{')[0].split('}')[-1].strip()
                if not ai_response:
                    ai_response = "Готово!"
            
            self.context.append({"role": "assistant", "content": ai_response})
            
            # Отображаем ответ
            self.add_to_chat("Мику", ai_response)
            
            # Эмоции
            self.set_emotion("happy")
            self.root.after(2000, lambda: self.set_emotion("default"))
            
        except Exception as e:
            self.add_to_chat("Ошибка", f"Не удалось обработать ответ: {str(e)}")
            self.set_emotion("default")

    def is_attempting_command(self, response):
        """Проверяет, не пытается ли ИИ выполнить команду без запроса"""
        if not isinstance(response, str):
            return False
            
        command_indicators = [
            "открываю",
            "запускаю",
            "выполняю",
            "включаю",
            "сейчас сделаю"
        ]
        
        return any(indicator in response.lower() for indicator in command_indicators)
        
        
    
#--------------------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = AnimeAssistant(root)
    root.mainloop()
