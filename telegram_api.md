# CactusPlugin: Взаимодействие с Telegram API (TLRPC)

Для продвинутых сценариев, выходящих за рамки простого ответа на команды, CactusLib предоставляет класс-помощник `CactusUtils.Telegram`. Он значительно упрощает прямое взаимодействие с методами Telegram API (TLRPC) и доступ к данным из кэша приложения.

Класс доступен через `self.utils.Telegram`. Его методы можно разделить на две категории:

1.  **Синхронные методы**: Быстро возвращают данные напрямую.
2.  **Асинхронные запросы**: Отправляют запрос в сеть и требуют `callback`-функцию для обработки ответа.

## Callback-функция
Асинхронные методы не возвращают результат сразу. Вместо этого они принимают функцию обратного вызова (callback), которая будет исполнена после получения ответа от серверов Telegram.

Эта функция всегда принимает два аргумента: `response` и `error`.

```python
def my_callback(response, error):
    # Если error не None, произошла ошибка
    if error:
        self.error(f"Произошла ошибка в API: {error.text}")
        self.utils.show_error(f"Ошибка: {error.text}")
        return

    # Если ошибки нет, обрабатываем успешный ответ
    # response содержит объект, который прислал Telegram
    self.info(f"Получен успешный ответ: {response}")
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
## Синхронные методы

Эти методы получают уже известные приложению данные и возвращают результат быстро.

### `get_user(user_id)`
Возвращает объект пользователя `TLRPC.User` из кэша.

```python
user = self.utils.Telegram.get_user(12345678)
if user:
    self.info(f"Имя пользователя: {user.first_name}")
```

### `peer(peer_id)` и `input_peer(peer_id)`
Получают объекты `Peer` и `InputPeer` соответственно. `InputPeer` необходим для большинства API-запросов, где нужно указать пользователя, чат или канал.

```python
# Получаем InputPeer для отправки запроса
user_input_peer = self.utils.Telegram.input_peer(12345678)
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

## Асинхронные запросы

### `get_chat(callback, chat_id)` и `get_channel(callback, channel_id)`
Получают полную информацию о чате или канале соответственно.

```python
def on_chat_info(response, error):
    if error: return
    # response.chats.get(0) будет содержать объект чата
    chat_title = response.chats.get(0).title
    self.utils.show_info(f"Полное инфо о чате: {chat_title}")

# ID чата всегда пишется с минусом вначале, но без 100, как в Bot API.
self.utils.Telegram.get_chat(on_chat_info, -1234567890)
```

### `get_user_photos(callback, user_id, limit)`
Получает фотографии профиля пользователя.

```python
def on_user_photos(response, error):
    if error: return
    # response - это объект photos.Photos
    photo_count = len(response.photos)
    self.utils.show_info(f"Найдено {photo_count} фото профиля.")

self.utils.Telegram.get_user_photos(on_user_photos, 12345678, limit=5)
```

### `get_sticker_set_by_short_name(callback, short_name)`
Получает информацию о наборе стикеров по его короткому имени (например, "Animals").

```python
def on_sticker_set(response, error):
    if error: return
    # response - это messages.StickerSet
    self.utils.show_info(f"Стикерпак '{response.set.title}' содержит {len(response.documents)} стикеров.")

self.utils.Telegram.get_sticker_set_by_short_name(on_sticker_set, "Animals")
```

