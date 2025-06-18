
# CactusPlugin: Вспомогательные утилиты (`CactusUtils`)

Класс `CactusUtils` (доступный в плагине через `self.utils`) содержит множество полезных статических методов и вложенных классов.

### Логирование

Для отладки плагинов используйте встроенный логгер, который пишет в Logcat с тегом вашего плагина и уровнем лога.
Это удобно для сбора и просмотра логов.

```python
# self.log(message, level) - основной метод
self.log("Подробное сообщение", "DEBUG")

# Упрощенные методы
self.debug("Это сообщение для отладки.")
self.info("Какая-то полезная информация.")
self.warn("Предупреждение о возможной проблеме.")
self.error("Произошла ошибка! " + traceback.format_exc())
```

Просмотреть логи можно командой `.logs` из самого CactusLib.

### Работа с файловой системой (`CactusUtils.FileSystem`)

Класс `CactusUtils.FileSystem` предоставляет безопасные методы для работы с файлами.

```python
# Путь к папке с файлами приложения
base_dir = self.utils.FileSystem.basedir()

# Создать и записать временный файл
content = "hello world"
temp_path = self.utils.FileSystem.write_temp_file("myfile.txt", content.encode("utf-8"))

# Удалить файл через 10 секунд
self.utils.FileSystem.delete_file_after(temp_path, 10)
```

Методы для работы с файлами:
- `write_temp_file(filename, content, mode="wb", delete_after=60)` - Создать файл в временной папке в кэше и записать в него содержимое, после чего удалить через заданное время(в секундах).
- `delete_file_after(path, delay)` - Удалить файл после заданной задержки.
- `get_file_content(path, mode="rb")` - Получить содержимое файла.
- `get_temp_file_content(filename, mode="rb", delete_after=60)` - Получить содержимое временного файла.

### Экранирование текста (`escape_html`)

Для безопасной вставки текста в сообщения с разметкой.

```python
# Для HTML
safe_html_fragment = self.utils.escape_html("<tag> & 'text'")
# результат: '&lt;tag&gt; &amp; 'text''
```

<details>
    <summary> <h3>Поиск сообщений (<code>search_messages</code>)</h3></summary>

Поиск сообщений в чате по различным критериям.

| Атрибут `SearchFilter` | Описание                                                                  |
| :------------------ | :------------------------------------------------------------------------ |
| `GIF`               | Поиск GIF-анимаций.                                                       |
| `MUSIC`             | Поиск аудиофайлов (музыки).                                               |
| `CHAT_PHOTOS`       | Поиск фотографий, отправленных в чате.                                   |
| `PHOTOS`            | Поиск фотографий.                                                        |
| `URL`               | Поиск сообщений, содержащих URL-ссылки.                                  |
| `DOCUMENT`          | Поиск документов.                                                         |
| `PHOTO_VIDEO`       | Поиск фотографий и видео.                                                |
| `PHOTO_VIDEO_DOCUMENT` | Поиск фотографий, видео и документов.                                    |
| `GEO`               | Поиск геопозиций.                                                         |
| `PINNED`            | Поиск закрепленных сообщений.                                             |
| `MY_MENTIONS`       | Поиск сообщений, в которых вас упомянули.                                 |
| `ROUND_VOICE`       | Поиск кружочков с голосовыми сообщениями.                                 |
| `CONTACTS`          | Поиск контактов.                                                          |
| `VOICE`             | Поиск голосовых сообщений.                                                |
| `VIDEO`             | Поиск видеосообщений.                                                     |
| `PHONE_CALLS`       | Поиск информации о звонках.                                              |
| `ROUND_VIDEO`       | Поиск кружочков с видеосообщениями.                                       |
| `EMPTY`             | Отсутствие фильтрации по типу контента (поиск по всем типам сообщений). |

##### Метод класса `search_messages`

```python
search_messages(
    callback: Callable[[List[MessageObject], Any], None],
    dialog_id: int,
    query: Optional[str] = None,
    from_id: Optional[int] = None,
    offset_id: int = 0,
    limit: int = 20,
    reply_message_id: Optional[int] = None,
    top_message_id: Optional[int] = None,
    filter: SearchFilter = SearchFilter.EMPTY,
)
```

Метод `search_messages` позволяет выполнять поиск сообщений в указанном диалоге с применением различных параметров фильтрации. Он асинхронно отправляет запрос и передает результаты через callback-функцию.

##### Параметры

* **`callback`** (`Callable[[List[MessageObject], Any], None]`): Функция обратного вызова, которая будет вызвана по завершении поиска. Она принимает два аргумента:
    * Список объектов `MessageObject`, если поиск успешен.
    * Объект ошибки (`Any`), если произошла ошибка.
* **`dialog_id`** (`int`): ID диалога (чата, канала, пользователя), в котором будет производиться поиск.
* **`query`** (`Optional[str]`, по умолчанию `None`): Строка запроса для поиска текста в сообщениях. Если `None`, поиск будет осуществляться по всем сообщениям, соответствующим другим фильтрам.
* **`from_id`** (`Optional[int]`, по умолчанию `None`): ID пользователя, от которого были отправлены искомые сообщения.
* **`offset_id`** (`int`, по умолчанию `0`): ID сообщения, с которого начинается поиск (для пагинации).
* **`limit`** (`int`, по умолчанию `20`): Максимальное количество сообщений для возврата.
* **`reply_message_id`** (`Optional[int]`, по умолчанию `None`): ID сообщения, на которое был дан ответ. Поиск будет осуществляться среди ответов на это сообщение.
* **`top_message_id`** (`Optional[int]`, по умолчанию `None`): ID верхнего сообщения в цепочке (обычно используется для поиска в тредах). Если указан `reply_message_id`, он будет иметь приоритет.
* **`filter`** (`SearchFilter`, по умолчанию `SearchFilter.EMPTY`): Тип контента, по которому будут фильтроваться сообщения. Используйте члены перечисления `SearchFilter`.

##### Пример использования

```python
from typing import List, Any
from org.telegram.messenger import MessageObject

def my_search_callback(messages: List[MessageObject], error: Any):
    if error:
        self.error(f"Ошибка при поиске сообщений: {error}")
    elif messages:
        self.info(f"Найдено {len(messages)} сообщений:")
        for msg in messages:
            self.info(f"- Сообщение ID: {msg.messageOwner.id}")
    else:
        self.warn("Сообщения не найдены.")

# Пример поиска 10 фотографий в диалоге с ID 12345
self.utils.Telegram.search_messages(
    callback=my_search_callback,
    dialog_id=12345,
    filter=SearchFilter.PHOTOS,
    limit=10
)

# Пример поиска сообщений, содержащих слово "привет", от пользователя с ID 67890
self.utils.Telegram.search_messages(
    callback=my_search_callback,
    dialog_id=12345,
    query="привет",
    from_id=67890
)
```
</details>


