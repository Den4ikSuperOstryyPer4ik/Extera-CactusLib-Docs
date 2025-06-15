
# CactusPlugin: Ответы на команды

CactusLib предоставляет несколько удобных методов для взаимодействия с пользователем в ответ на его команду. Все эти методы требуют объект `params` из экземпляра `CactusUtils.Command`.

### `HookResult` и `HookStrategy`

Ваша функция команды должна возвращать объект `HookResult`, чтобы контролировать, что произойдет с исходным сообщением пользователя.

  - `HookResult(strategy=HookStrategy.CANCEL)`: **Отменяет** отправку исходного сообщения. Используйте это, когда ваш плагин отправляет собственный ответ (`answer`) или выполняет действие, не требующее отправки текста.
  - `HookResult(strategy=HookStrategy.MODIFY, params=...)`: **Изменяет** исходное сообщение. Используйте с `edit_message`.
  - `HookResult()` (пустой): Ничего не делает, сообщение пользователя отправится как есть. Возвращайте это, если ваша команда не должна была сработать в данном контексте.

### Редактирование отправляемого сообщения: `edit_message`

Этот метод изменяет текст исходного сообщения пользователя. Идеально для простых команд, где ответ заменяет текст сообщения.

```python
def edit_message(self, params, text: str, parse_markdown: bool = True, parse_mode: str = "MARKDOWN", **kwargs)
```

**Пример:**

```python
@command("ping")
def handle_ping(self, command: CactusUtils.Command):
    # command.params передается из аргумента команды
    return self.edit_message(command.params, "<b>pong!</b>", parse_mode="HTML")
```

### Отправка нового сообщения: `answer`

Этот метод отправляет новое сообщение в чат в ответ на команду (как правило, с реплаем).

```python
def answer(self, params, text: str, *, parse_markdown: bool = True, parse_mode: str = "MARKDOWN", **kwargs)
```

**Пример:**

```python
@command("say")
def handle_say(self, command: CactusUtils.Command):
    # Отвечаем текстом, который был в аргументах
    self.answer(command.params, f"Вы сказали: {command.raw_args}")
    # Отменяем отправку исходного ".say ..."
    return HookResult(strategy=HookStrategy.CANCEL)
```

### Отправка файла: `answer_file`

Отправляет документ (файл) с возможностью добавить подпись.

```python
def answer_file(self, params, path: str, caption: Optional[str] = None, *, parse_markdown: bool = True, **kwargs)
```

**Пример:**

```python
@command("getlogs")
def handle_logs(self, command: CactusUtils.Command):
    log_content = "some log data..."
    # Записываем контент во временный файл
    file_path = self.utils.FileSystem.write_temp_file("logs.txt", log_content.encode("utf-8"))

    self.answer_file(command.params, file_path, caption="Вот ваши логи:")
    
    # Удаляем файл через 15 секунд
    self.utils.FileSystem.delete_file_after(file_path, 15)

    return HookResult(strategy=HookStrategy.CANCEL)
```

### Отправка фото: `answer_photo`

Отправляет изображение.

```python
def answer_photo(self, params, path: str, caption: Optional[str] = None, *, parse_markdown: bool = True, **kwargs)
```

**Пример:**

```python
@command("cat")
def handle_cat(self, command: CactusUtils.Command):
    # Предполагается, что у вас есть путь к картинке
    cat_pic_path = "/path/to/cat.jpg"
    self.answer_photo(command.params, cat_pic_path, caption="Держи котика!")
    return HookResult(strategy=HookStrategy.CANCEL)
```
