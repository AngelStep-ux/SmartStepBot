import psycopg2
import requests
import telebot
import random
from telebot import types, TeleBot, custom_filters
from telebot.handler_backends import State, StatesGroup
from data_base import host, user, password, db_name


connection = None

try:
    connection = psycopg2.connect(
        host=host, user=user, password=password, database=db_name
    )

    connection.autocommit = True

    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")

        print(f"Server version: {cursor.fetchone()}")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS word_set (
                id SERIAL PRIMARY KEY,
                english_word VARCHAR(50) UNIQUE NOT NULL,
                translation VARCHAR(50) NOT NULL
            );
        """
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_words (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                word_id INT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES telegram_users(user_id),
                FOREIGN KEY (word_id) REFERENCES word_set(id)
            );
        """
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_users (
                user_id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                word_count INTEGER DEFAULT 0
            );
        """
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_words (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES telegram_users(user_id),
                word_id INTEGER NOT NULL REFERENCES word_set(id)
            );
        """
        )

    eng_words = [
        "run",
        "beautiful",
        "quickly",
        "book",
        "happy",
        "dance",
        "friend",
        "carefully",
        "write",
        "strong",
        "city",
        "easily",
        "play",
        "interesting",
        "house",
        "room",
        "prepare",
    ]

    rus_words = [
        "бегать",
        "красивый",
        "быстро",
        "книга",
        "счастливый",
        "танцевать",
        "друг",
        "осторожно",
        "писать",
        "сильный",
        "город",
        "легко",
        "играть",
        "интересный",
        "дом",
        "комната",
        "готовиться",
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO word_set (english_word, translation) 
            VALUES(%s, %s) ON CONFLICT DO NOTHING;
        """,
            [(eng_word, rus_word) for eng_word, rus_word in zip(eng_words, rus_words)],
        )

        print("[INFO] Data was successfully inserted")

except Exception as _ex:
    print("[INFO] Error while working with PostgreSQL", _ex)
finally:
    if connection:
        connection.close()

TOKEN = "1234567890"

bot = telebot.TeleBot(TOKEN)

known_users = []
userStep = {}
buttons = []


class Command:
    ADD_WORD = "Добавить слово ➕"
    DELETE_WORD = "Удалить слово🔙"
    NEXT = "Дальше ⏭"


class MyStates(StatesGroup):
    target_word = State()
    russian_word = State()
    other_words = State()
    delete_word = State()
    adding_word = State()
    adding_translation = State()


def fetch_user_id(connection, telegram_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM telegram_users WHERE telegram_id = %s;", (telegram_id,)
        )
        user_id = cursor.fetchone()
        return user_id[0] if user_id else None


def get_user_step(uid):
    if uid in userStep:
        return userStep[uid]
    else:
        known_users.append(uid)
        userStep[uid] = 0
        print('New user detected, who hasn\'t used "/start" yet')
        return 0


def get_random_word_from_db():
    connection = None
    try:
        connection = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            database=db_name,
            client_encoding="utf8",
        )

        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT translation, english_word FROM word_set ORDER BY RANDOM() LIMIT 1;"
            )
            result = cursor.fetchone()
            if result:
                return result[0], result[1]
            return None, None

    except Exception as ex:
        print("[INFO] Error while fetching random word from PostgreSQL", ex)
        return None, None
    finally:
        if connection:
            connection.close()


def get_other_words_from_db(target_word):
    try:
        connection = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            database=db_name,
            client_encoding="utf8",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT english_word 
                FROM word_set 
                WHERE english_word != %s 
                ORDER BY RANDOM() 
                LIMIT 3;
            """,
                (target_word,),
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception as ex:
        print("[INFO] Error while fetching other words from PostgreSQL", ex)
        return []
    finally:
        if connection:
            connection.close()


def get_usage_example(word):
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        for meaning in data[0]["meanings"]:
            for definition in meaning["definitions"]:
                if "example" in definition:
                    return definition["example"]

    else:
        print(f"Ошибка: {response.status_code}")
        return None


@bot.message_handler(commands=["cards", "start"])
def start_bot(message):
    cid = message.chat.id

    if cid not in known_users:
        known_users.append(cid)
        userStep[cid] = 0

        bot.send_message(
            message.chat.id,
            f"Привет, <b>{message.from_user.first_name}</b>.\n"
            "Давай попрактикуемся в английском языке!\n"
            "\n"
            "У тебя есть возможность использовать тренажёр, как конструктор, и собирать свою собственную базу для обучения.\n"
            "Для этого воспользуйся инструментами:\n"
            "<i>Добавить слово ➕</i>,\n"
            "<i>Удалить слово 🔙</i>.\n"
            "\n"
            "Отправь мне /help, если нужна помощь.\n"
            "Удачи! 😊",
            parse_mode="HTML",
        )

    show_next_word(message)


def show_next_word(message):
    try:
        russian_word, target_word = get_random_word_from_db()
        if not russian_word or not target_word:
            bot.send_message(message.chat.id, "В базе нет слов. Добавьте новые слова.")
            return

        other_words = get_other_words_from_db(target_word)

        markup = types.ReplyKeyboardMarkup(row_width=2)
        target_word_btn = types.KeyboardButton(target_word)
        other_words_btns = [types.KeyboardButton(word) for word in other_words]

        buttons = [target_word_btn] + other_words_btns
        random.shuffle(buttons)

        next_btn = types.KeyboardButton(Command.NEXT)
        add_word_btn = types.KeyboardButton(Command.ADD_WORD)
        delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
        buttons.extend([next_btn, add_word_btn, delete_word_btn])

        markup.add(*buttons)

        bot.send_message(
            message.chat.id,
            f"Угадай слово: <b>{russian_word}</b>",
            reply_markup=markup,
            parse_mode="HTML",
        )
        bot.set_state(message.from_user.id, MyStates.target_word, message.chat.id)
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            data["target_word"] = target_word
            data["russian_word"] = russian_word
            data["other_words"] = other_words

    except Exception as _ex:
        print(f"Error in show_next_word: {_ex}")


@bot.message_handler(commands=["help"])
def help_bot(message):
    bot.send_message(
        message.chat.id,
        "<b>Используй команды</b> 💬:\n"
        "/start и /cards - начать обучение\n"
        "/all_words - посмотреть весь список слов\n"
        "\n"
        "<b>Используй кнопки:</b>\n"
        "<i>Добавить слово➕\n</i>"
        "<i>Удалить слово🔙\n</i>"
        "<i>Дальше ⏭\n</i>"
        "\n"
        "Эти функции помогут тебе создать свою собственную базу данных для обучения!\n"
        "Удачи! 😊",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["all_words"])
def send_all_words(message):
    cid = message.chat.id
    user_id = message.from_user.id

    try:
        connection = psycopg2.connect(
            host=host, user=user, password=password, database=db_name
        )
        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, english_word, translation FROM word_set;
            """
            )
            all_words = cursor.fetchall()

            cursor.execute(
                """
                SELECT word_id FROM user_words WHERE user_id = (SELECT user_id FROM telegram_users WHERE telegram_id = %s);
            """,
                (user_id,),
            )
            user_words_ids = cursor.fetchall()

            user_words_set = {word_id[0] for word_id in user_words_ids}

            cursor.execute(
                """
                SELECT word_id FROM deleted_words WHERE user_id = (SELECT user_id FROM telegram_users WHERE telegram_id = %s);
            """,
                (user_id,),
            )
            deleted_words_ids = cursor.fetchall()

            deleted_words_set = {word_id[0] for word_id in deleted_words_ids}

            combined_words = {}

            for word in all_words:
                word_id, english_word, translation = word
                if word_id in user_words_set and word_id not in deleted_words_set:
                    combined_words[
                        english_word
                    ] = translation
                elif word_id not in deleted_words_set:
                    combined_words[english_word] = translation

            if combined_words:
                response = "Вот все слова, которые Вы изучаете:\n"
                for word, translation in combined_words.items():
                    response += f"{word}: {translation}\n"
            else:
                response = "У Вас пока нет изученных слов."

            bot.send_message(cid, response)
            help_bot(message)

    except Exception as _ex:
        print("[INFO] Error while working with PostgreSQL", _ex)
        bot.send_message(cid, "Произошла ошибка при получении слов. Попробуйте снова.")
    finally:
        if connection:
            connection.close()


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    show_next_word(message)


@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message):
    bot.set_state(message.from_user.id, MyStates.adding_word, message.chat.id)
    bot.send_message(
        message.chat.id,
        "Пожалуйста, введите английское слово, которое хотите добавить:",
    )


@bot.message_handler(state=MyStates.adding_word)
def get_english_word(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data["english_word"] = message.text
    bot.set_state(message.from_user.id, MyStates.adding_translation, message.chat.id)
    bot.send_message(message.chat.id, "Теперь введите перевод на русский язык:")


@bot.message_handler(state=MyStates.adding_translation)
def get_translation(message):
    cid = message.chat.id
    user_id = message.from_user.id

    try:
        with bot.retrieve_data(user_id, cid) as data:
            english_word = data["english_word"]
            russian_word = message.text

            connection = psycopg2.connect(
                host=host, user=user, password=password, database=db_name
            )
            connection.autocommit = True

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM user_words uw
                    JOIN word_set w ON uw.word_id = w.id
                    WHERE uw.user_id = (SELECT user_id FROM telegram_users WHERE telegram_id = %s)
                    AND w.english_word = %s;
                    """,
                    (user_id, english_word),
                )
                word_exists = cursor.fetchone()[0] > 0

                if word_exists:
                    bot.send_message(
                        cid,
                        f"Слово '{english_word}' уже существует в Вашей базе данных.",
                    )
                    return

                cursor.execute(
                    "INSERT INTO word_set (english_word, translation) VALUES (%s, %s) RETURNING id;",
                    (english_word, russian_word),
                )
                word_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT INTO telegram_users (telegram_id) VALUES (%s) "
                    "ON CONFLICT (telegram_id) DO NOTHING RETURNING user_id;",
                    (user_id,),
                )
                result = cursor.fetchone()

                if result:
                    db_user_id = result[0]
                else:
                    cursor.execute(
                        "SELECT user_id FROM telegram_users WHERE telegram_id = %s;",
                        (user_id,),
                    )
                    db_user_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT INTO user_words (user_id, word_id) VALUES (%s, %s);",
                    (db_user_id, word_id),
                )

                cursor.execute("SELECT COUNT(*) FROM word_set;")
                total_word_count = cursor.fetchone()[0]

            bot.send_message(
                cid,
                f"Слово '{english_word}' с переводом '{russian_word}' успешно добавлено!",
            )
            bot.send_message(
                cid, f"Вы изучаете {total_word_count} слов(а). Так держать!"
            )
            bot.delete_state(user_id, cid)

    except Exception as _ex:
        print("[INFO] Error while working with PostgreSQL", _ex)
        bot.send_message(
            cid, "Произошла ошибка при добавлении слова. Попробуйте снова."
        )

    finally:
        if connection:
            connection.close()
        bot.delete_state(user_id, cid)
        show_next_word(message)


@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def delete_word(message):
    bot.send_message(message.chat.id, "Введите слово, которое хотите удалить:")
    bot.set_state(message.from_user.id, MyStates.delete_word, message.chat.id)


@bot.message_handler(state=MyStates.delete_word)
def process_delete_word(message):
    try:
        connection = psycopg2.connect(
            host=host, user=user, password=password, database=db_name
        )
        connection.autocommit = True

        user_id = fetch_user_id(
            connection, message.from_user.id
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id FROM word_set WHERE english_word = %s;""", (message.text,)
            )
            word_id = cursor.fetchone()

            if word_id:
                word_id = word_id[0]

                cursor.execute(
                    """DELETE FROM user_words 
                       WHERE user_id = %s 
                       AND word_id = %s
                       RETURNING word_id;""",
                    (user_id, word_id),
                )
                deleted_word_id = cursor.fetchone()

                if deleted_word_id:
                    cursor.execute(
                        """INSERT INTO deleted_words (user_id, word_id) VALUES (%s, %s);""",
                        (user_id, word_id),
                    )
                    bot.send_message(
                        message.chat.id, f"Слово '{message.text}' было удалено."
                    )
                else:
                    bot.send_message(
                        message.chat.id, "Такое слово не найдено в Вашей базе данных."
                    )
            else:
                bot.send_message(message.chat.id, "Такое слово не найдено в словаре.")

    except Exception as _ex:
        print("[INFO] Error while working with PostgreSQL", _ex)
        bot.send_message(
            message.chat.id, "Произошла ошибка при удалении слова. Попробуйте снова."
        )

    finally:
        if connection:
            connection.close()
        bot.delete_state(message.from_user.id, message.chat.id)
        show_next_word(message)


@bot.message_handler(func=lambda message: True, content_types=["text"])
def check_answer(message):
    try:
        if message.text in [Command.ADD_WORD, Command.DELETE_WORD, Command.NEXT]:
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            target_word = data["target_word"]

        if message.text == target_word:
            bot.send_message(message.chat.id, "Верно! Excellent! 🌟")
            example = get_usage_example(target_word)
            bot.send_message(
                message.chat.id, f"<b>Пример</b> 📖:<i>{example}</i>", parse_mode="HTML"
            )
            show_next_word(message)
        else:
            bot.send_message(message.chat.id, "Ошибка. Попробуй еще раз)")

    except Exception as _ex:
        print(f"Error checking answer: {_ex}")


if __name__ == "__main__":
    print("Бот запущен! Ура!")
    bot.add_custom_filter(custom_filters.StateFilter(bot))
    bot.infinity_polling(skip_pending=True)
