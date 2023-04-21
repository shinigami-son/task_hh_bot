import sys
import os
import config
import logging
import requests
from quizzer import Quiz
from aiogram import Bot, Dispatcher, executor, types
from functions import get_all_exchange_rates_erapi, convert_currency_erapi
import random

logging.basicConfig(level=logging.INFO)


bot = Bot(token=config.TOKEN)
db = Dispatcher(bot)
quizzes_database = {}
quizzes_owners = {}


@db.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):

    kb = [
        [types.KeyboardButton(text="Погода")],
        [types.KeyboardButton(text="Конвертер валют")],
        [types.KeyboardButton(text="Случайная картинка")],
        [types.KeyboardButton(text="Создать опрос")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.reply(r"Привет. Выбери, что мне сделать", reply_markup=keyboard)


@db.message_handler(commands=['weather'])
async def weather(message: types.Message):
    try:
        searchQuery = message.text[8:] # Срезаем нужную нам часть запроса
        appid = '27fb079e41d695b0d1ed5e37f9cf4a9d'
        res = requests.get("http://api.openweathermap.org/data/2.5/weather", params={'q': searchQuery, 'units': 'metric', 'lang': 'ru', 'APPID': appid})
        data = res.json()
        message_weather = "conditions:" + str(data['weather'][0]['description']) + "\ntemp:" + str(data['main']['temp']) +  "\ntemp_min:" +str(data['main']['temp_min']) + "\ntemp_max:" + str(data['main']['temp_max'])
        await message.reply(message_weather)
    except Exception as e:
        print("Exception (weather):", e)
        pass


@db.message_handler(commands=['currency'])
async def currency(message: types.Message):
    searchQuery = message.text[9:].split() # Разделяем запрос на части
    source_currency = searchQuery[0]
    destination_currency = searchQuery[1]
    amount = float(searchQuery[2])
    last_updated_datetime, exchange_rate = convert_currency_erapi(source_currency, destination_currency, amount)
    message_currency = f"{amount} {source_currency} = {exchange_rate} {destination_currency}"
    await message.reply(message_currency)


@db.message_handler(commands=['picture'])
async def picture(message: types.Message):
    photo = open('photo/' + random.choice(os.listdir('photo')), 'rb')
    await bot.send_photo(chat_id=message.chat.id, photo=photo)


@db.poll_answer_handler()
async def handle_poll_answer(quiz_answer: types.PollAnswer):
    quiz_owner = quizzes_owners.get(quiz_answer.poll_id)
    if not quiz_owner:
        logging.error(f"Не могу найти автора викторины с quiz_answer.poll_id = {quiz_answer.poll_id}")
        return
    for saved_quiz in quizzes_database[quiz_owner]:
        if saved_quiz.quiz_id == quiz_answer.poll_id:
            # Проверяем, прав ли пользователь. В викторине (пока) один ответ, поэтому можно спокойно взять 0-й элемент ответа
            if saved_quiz.correct_option_id == quiz_answer.option_ids[0]:
                # Если прав, то добавляем в список
                saved_quiz.winners.append(quiz_answer.user.id)
                # По нашему условию, если есть двое правильно ответивших, закрываем викторину.
                if len(saved_quiz.winners) == 2:
                    await bot.stop_poll(saved_quiz.chat_id, saved_quiz.message_id)


@db.poll_handler(lambda active_quiz: active_quiz.is_closed is True)
async def just_poll_answer(active_quiz: types.Poll):
    quiz_owner = quizzes_owners.get(active_quiz.id)
    if not quiz_owner:
        logging.error(f"Не могу найти автора викторины с active_quiz.id = {active_quiz.id}")
        return
    for num, saved_quiz in enumerate(quizzes_database[quiz_owner]):
        if saved_quiz.quiz_id == active_quiz.id:
            # Используем ID победителей, чтобы получить по ним имена игроков и поздравить.
            congrats_text = []
            for winner in saved_quiz.winners:
                chat_member_info = await bot.get_chat_member(saved_quiz.chat_id, winner)
                congrats_text.append(chat_member_info.user.get_mention(as_html=True))

            await bot.send_message(saved_quiz.chat_id, "Викторина закончена, всем спасибо! Вот наши победители:\n\n"
                                   + "\n".join(congrats_text), parse_mode="HTML")
            # Удаляем викторину из обоих наших "хранилищ"
            del quizzes_owners[active_quiz.id]
            del quizzes_database[quiz_owner][num]


@db.message_handler(commands=["polls"])
async def cmd_start(message: types.Message):
    if message.chat.type == types.ChatType.PRIVATE:
        poll_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        poll_keyboard.add(types.KeyboardButton(text="Создать викторину",
                                               request_poll=types.KeyboardButtonPollType(type=types.PollType.QUIZ)))
        poll_keyboard.add(types.KeyboardButton(text="Отмена"))
        await message.answer("Нажмите на кнопку ниже и создайте викторину! "
                             "Внимание: в дальнейшем она будет публичной (неанонимной).", reply_markup=poll_keyboard)
    else:
        words = message.text.split()
        # Только команда /polls без параметров. В этом случае отправляем в личные сообщения с ботом.
        if len(words) == 1:
            bot_info = await bot.get_me()
            keyboard = types.InlineKeyboardMarkup()
            move_to_dm_button = types.InlineKeyboardButton(text="Перейти в ЛС",
                                                           url=f"t.me/{bot_info.username}?start=anything")
            keyboard.add(move_to_dm_button)
            await message.reply("Не выбрана ни одна викторина. Пожалуйста, перейдите в личные сообщения с ботом, "
                                "чтобы создать новую.", reply_markup=keyboard)
        # Если у команды /polls есть параметр, то это, скорее всего, ID викторины.
        # Проверяем и отправляем.
        else:
            quiz_owner = quizzes_owners.get(words[1])
            if not quiz_owner:
                await message.reply("Викторина удалена, недействительна или уже запущена в другой группе. Попробуйте создать новую.")
                return
            for saved_quiz in quizzes_database[quiz_owner]: # Проходим по всем сохранённым викторинам от конкретного user ID
                if saved_quiz.quiz_id == words[1]: # Нашли нужную викторину, отправляем её.
                    msg = await bot.send_poll(chat_id=message.chat.id, question=saved_quiz.question,
                                              is_anonymous=False, options=saved_quiz.options, type="quiz",
                                              correct_option_id=saved_quiz.correct_option_id)
                    quizzes_owners[msg.poll.id] = quiz_owner # ID викторины при отправке уже другой, создаём запись.
                    del quizzes_owners[words[1]] # Старую запись удаляем.
                    saved_quiz.quiz_id = msg.poll.id # В "хранилище" викторин тоже меняем ID викторины на новый
                    saved_quiz.chat_id = msg.chat.id  # ... а также сохраняем chat_id ...
                    saved_quiz.message_id = msg.message_id # ... и message_id для последующего закрытия викторины.


@db.message_handler(lambda message: message.text == "Отмена")
async def action_cancel(message: types.Message):
    remove_keyboard = types.ReplyKeyboardRemove()
    await message.answer("Действие отменено. Введите /polls, чтобы начать заново.", reply_markup=remove_keyboard)


@db.message_handler(content_types=["poll"])
async def msg_with_poll(message: types.Message):
    # Если пользователь раньше не присылал запросы, выделяем под него запись
    if not quizzes_database.get(str(message.from_user.id)):
        quizzes_database[str(message.from_user.id)] = []
    # Если пользователь решил вручную отправить не викторину, а опрос, откажем ему.
    if message.poll.type != "quiz":
        await message.reply("Извините, я принимаю только викторины (quiz)!")
        return
    # Сохраняем себе викторину в память
    quizzes_database[str(message.from_user.id)].append(Quiz(
        quiz_id=message.poll.id,
        question=message.poll.question,
        options=[o.text for o in message.poll.options],
        correct_option_id=message.poll.correct_option_id,
        owner_id=message.from_user.id)
    )
    # Сохраняем информацию о её владельце для быстрого поиска в дальнейшем
    quizzes_owners[message.poll.id] = str(message.from_user.id)

    await message.reply(
        f"Викторина сохранена. Общее число сохранённых викторин: {len(quizzes_database[str(message.from_user.id)])}")


@db.inline_handler()
async def inline_query(query: types.InlineQuery): # Обработчик любых инлайн-запросов
    results = []
    user_quizzes = quizzes_database.get(str(query.from_user.id))
    if user_quizzes:
        for quiz in user_quizzes:
            keyboard = types.InlineKeyboardMarkup()
            start_quiz_button = types.InlineKeyboardButton(
                text="Отправить в группу",
                url=await deep_linking.get_startgroup_link(quiz.quiz_id)
            )
            keyboard.add(start_quiz_button)
            results.append(types.InlineQueryResultArticle(
                id=quiz.quiz_id,
                title=quiz.question,
                input_message_content=types.InputTextMessageContent(
                    message_text="Нажмите кнопку ниже, чтобы отправить викторину в группу."),
                reply_markup=keyboard
            ))
    await query.answer(switch_pm_text="Создать викторину", switch_pm_parameter="_",
                       results=results, cache_time=120, is_personal=True)


@db.message_handler()
async def version(message: types.Message):
    if message.text == 'Погода':
        await message.answer("Чтобы узнать прогноз погоды в вашем городе напишите команду '/weather' в формате '/weather Moscow, ru'")
    elif message.text == 'Конвертер валют':
        await message.answer("Чтобы сконвертировать валюты напишите команду '/currency' в формате '/currency USD EUR 1000'")
    elif message.text == 'Случайная картинка':
        await message.answer("Для получения случайного изображения введите команду '/picture'")
    elif message.text == 'Создать опрос':
        await message.answer("Для создания опроса введите команду '/polls'")
    else:
        pass


if __name__ == '__main__':
    executor.start_polling(db, skip_updates=True)
