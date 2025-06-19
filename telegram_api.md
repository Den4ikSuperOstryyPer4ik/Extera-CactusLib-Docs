# CactusPlugin: Взаимодействие с Telegram API (TLRPC)

Для продвинутых сценариев CactusLib предоставляет класс-помощник `CactusUtils.Telegram`. Он значительно упрощает прямое взаимодействие с методами Telegram API (TLRPC), предлагая **синхронный** способ выполнения запросов, более привычный для разработчиков и готовые методы-обертки для популярных запросов.

Вместо использования callback-функций, теперь вы можете отправлять запросы и получать результат напрямую, обрабатывая ошибки через стандартный механизм `try...except` или самостоятельно без этого.

Класс доступен через `self.utils.Telegram`.

## Основной метод: `send` (aka `send_request`)

Это центральный метод для выполнения всех API-запросов. Большинство других методов в этом классе являются лишь удобными обертками над ним.

**Сигнатура:**
```python
def send(req, *, wait_response: bool = True, timeout: int = 7, raise_errors: bool = True) -> Union[int, Result]: ...
```
-   `req`: Полностью сформированный объект запроса `TLRPC`.
-   `wait_response` (`bool`): Если `True` (по умолчанию), метод будет ожидать ответа от Telegram и вернет результат. Если `False`, метод не будет ждать и сразу вернет ID запроса.
-   `timeout` (`int`): Максимальное время ожидания ответа в секундах.
-   `raise_errors` (`bool`): Если `True` (по умолчанию), в случае ошибки от API будет выброшено исключение `TLRPCException`. Если `False`, метод вернет объект `Result` с заполненным полем `.error`.
-   `callback` (`Optional[Callable[[Any, Any], None]`): Если указана и `wait_response=False`, метод вызовет переданную функцию с результатом запроса и ошибкой (если есть) в качестве аргументов.
```python
class Result:
    req_id: int
    error: Optional[TLRPC.TL_error]
    response: Optional[TLObject]
```

### Синхронный запрос (стандартное поведение)

Это основной способ использования. Выполнение кода приостанавливается до получения ответа или истечения таймаута.

```python
# Создаем запрос для получения информации о чате по его ID
req = TLRPC.TL_messages_getChats()
req.id.add(-123456789)

try:
    # Отправляем запрос и ждем результат
    result = self.utils.Telegram.send(req)
    
    # result - это объект Result, содержащий ответ
    chat.title = result.response.chats.get(0)
    self.utils.show_info(f"Чат: {chat.title}")

except self.utils.Telegram.TLRPCException as e:
    # Перехватываем ошибки, если API вернул ошибку
    self.error(f"Ошибка API {e.error.code}: {e.error.text}")

except TimeoutError:
    # Перехватываем ошибку, если сервер не ответил вовремя
    self.error("Сервер не ответил на запрос.")
```

### Запрос "Fire-and-Forget" (без ожидания ответа)

Используйте `wait_response=False`, если вам не важен результат запроса, и вы не хотите блокировать выполнение кода.

```python
# Пример: отправка статуса оффлайн
req = self.utils.Telegram.tlrpc_object(
    TL_account.updateStatus(),
    offline=True
)

# Отправляем запрос и не ждем ответа
self.utils.Telegram.send(req, wait_response=False)
```
### Использование callback (как обычно)
Если вы предпочитаете использовать callback-функции, вы можете передать их в метод `send` как аргумент `callback`.
```python
def on_chat_info(response, error):
    if error: return
    # response в данном случае - это объект TLRPC.messages_Chats
    chat_title = response.chats.get(0).title
    self.utils.show_info(f"Имя чата: {chat_title}")

# Отправляем запрос и передаем callback-функцию
self.utils.Telegram.send(req, wait_response=False, callback=on_chat_info)
```

## Вспомогательные методы

### `tlrpc_object(request_class, **kwargs)`
Ключевой метод-помощник для создания и заполнения любого объекта запроса `TLRPC`.

Вместо того чтобы писать:
```python
req = TLRPC.TL_photos_getUserPhotos()
req.user_id = self.utils.Telegram.input_peer(user_id)
req.limit = 5
```

Можно написать короче:
```python
req = self.utils.Telegram.tlrpc_object(
    TLRPC.TL_photos_getUserPhotos(),
    user_id=self.utils.Telegram.input_peer(user_id),
    limit=5
)
```
## Готовые методы-обертки

Эти методы упрощают вызов популярных эндпоинтов API. Они используют `send` "под капотом", поэтому вы можете передавать в них его аргументы (`timeout`, `raise_errors` и т.д.).

### `search_messages(...)`

Выполняет поиск сообщений в диалоге по множеству критериев.

-   `dialog_id` (`int`): ID диалога для поиска.
-   `query` (`str`): Текстовый запрос.
-   `from_id` (`int`): ID отправителя.
-   `filter` (`SearchFilter`): Фильтр типа сообщений (см. ниже).
-   `limit` (`int`): Количество сообщений для возврата.
-   `offset` (`int`): Смещение для начала поиска.


Возвращает список объектов `org.telegram.messenger.MessageObject`.

**`SearchFilter`** - это `Enum` для удобного выбора фильтра.
Примеры значений: `SearchFilter.PHOTO_VIDEO`, `SearchFilter.URL`, `SearchFilter.MUSIC`, `SearchFilter.EMPTY` и другие.

```python
try:
    # Ищем последние 5 сообщений с URL в текущем чате
    found_messages = self.utils.Telegram.search_messages(
        dialog_id=command.params.peer,
        filter=self.utils.Telegram.SearchFilter.URL,
        limit=5
    )
    self.answer(command.params, f"Найдено ссылок: {len(found_messages)}")
except self.utils.Telegram.TLRPCException as e:
    self.answer(command.params, f"Ошибка поиска: {e.error.text}")
```

### `get_chat(...)` и `get_channel(...)`
Получают полную информацию о чате или канале.

```python
try:
    result = self.utils.Telegram.get_chat(-10012345678)
    chat_title = result.response.chats.get(0).title
    self.utils.show_info(f"Информация о чате: {chat_title}")
except self.utils.Telegram.TLRPCException as e:
    self.error(f"Не удалось получить информацию о чате: {e.error.text}")

```

### `get_user_photos(...)`
Получает фотографии профиля пользователя.

```python
try:
    result = self.utils.Telegram.get_user_photos(user_id, limit=3)
    photo_count = len(result.response.photos)
    self.utils.show_info(f"Найдено {photo_count} фото.")
except self.utils.Telegram.TLRPCException as e:
    self.error(f"Не удалось получить фото: {e.error.text}")
```

### `get_sticker_set_by_short_name(...)`
Получает информацию о наборе стикеров по его короткому имени.
Короткое имя - это часть URL стикерпака, например, `CactusPlugins` в `t.me/addstickers/CactusPlugins`.

```python
try:
    result = self.utils.Telegram.get_sticker_set_by_short_name("CactusPlugins")
    sticker_set = result.response.set
    self.utils.show_info(f"Найден стикерпак: {sticker_set.title}")
except self.utils.Telegram.TLRPCException as e:
    self.error(f"Стикерпак не найден: {e.error.text}")
```

### `delete_messages(messages, chat_id, ...)`
Удаляет сообщения в чате.

-   `messages` (`List[int]`): Список ID сообщений для удаления.
-   `chat_id` (`int`): ID чата, в котором нужно удалить сообщения.

```python
# Удаляем сообщения с ID 101 и 102 в текущем чате
messages_to_delete = [101, 102]
self.utils.Telegram.delete_messages(messages_to_delete, command.params.peer)
```

## Доступ к кэшу

Эти методы получают данные из локального кэша приложения и работают мгновенно.

-   `get_user(user_id)`: Возвращает объект `TLRPC.User`.
-   `input_user(user_id)`: Возвращает `TLRPC.InputUser` для использования в запросах.
-   `peer(peer_id)`: Возвращает `TLRPC.Peer`.
-   `input_peer(peer_id)`: Возвращает `TLRPC.InputPeer` для использования в запросах.