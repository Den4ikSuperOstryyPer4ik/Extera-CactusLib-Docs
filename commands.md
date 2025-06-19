
# CactusPlugin: Команды

Объявить команду в классе можно с помощью декоратора `@command`.

### Структура декоратора

```python
def command(
    command: Optional[str] = None, *,
    aliases: Optional[List[str]] = None,
    doc: Optional[str] = None,
    enabled: Optional[Union[str, bool]] = None
): ...
```

  - `command` (`str`, optional): Основное имя команды. Если не указано, используется имя метода.
  - `aliases` (`list[str]`, optional): Список альтернативных имен (псевдонимов) для команды.
  - `doc` (`str`, optional): Ключ для строки из вашего словаря `strings`, которая описывает команду. Это описание будет видно в меню помощи (`.chelp`).
  - `enabled` (`str` | `bool`, optional): Управляет доступностью команды. Можно передать `False` для полного отключения или строку-ключ от настройки (из `create_settings`), которая будет включать/выключать команду.

### Аргумент функции

В декорированную функцию передается объект `Command`, содержащий всю информацию о вызванной команде.

```python
@dataclass
class Command:
    command: str  # Какая именно команда или алиас были вызваны
    raw_args: Optional[str]  # Всё, что идёт после команды в виде единой строки
    args: List[str]  # Аргументы, разделенные по пробелам. Аргументы в кавычках (" ") считаются единым целым.
    text: str  # Полный исходный текст сообщения
    account: int  # Индекс текущего аккаунта
    params: Any  # Объект с параметрами отправляемого сообщения (peer, replyToMsg и т.д.), необходимый для ответа или редактирования
```

### Примеры

1.  **Простая команда с псевдонимом:**
    Каждый раз, когда пользователь будет писать `.ping` или `.пинг`, его сообщение при отправке будет изменено на "pong\!".

    ```python
    @command("ping", aliases=["пинг"])
    def handle_ping(self, command: CactusUtils.Command):
        # edit_message редактирует отправляемое сообщение пользователя
        return self.edit_message(command.params, "pong!")
    ```

2.  **Команда с аргументами и документацией:**
    Эта команда будет называться `logs` (т.к. имя не указано в декораторе) и будет доступна по префиксу (например, `.logs`). Её описание будет браться из `strings` по ключу `cmd_logs_doc` в локали системы.

    ```python
    @command(doc="cmd_logs_doc")
    def logs(self, command: CactusUtils.Command):
        # command.args содержит список аргументов
        if not command.args:
            text = self.string("no_args")
        else:
            text = self._get_logs_from_somewhere(command.args)

        # answer отправляет новый ответ в чат
        self.answer(command.params, text)

        # Отменяем отправку оригинального сообщения с командой
        return HookResult(strategy=HookStrategy.CANCEL)
    ```

3.  **Команда, зависимая от настройки:**
    Эта команда будет работать только если в настройках плагина опция `test_command` включена. (Она должна являться `Switch`'ем)

    ```python
    @command(enabled="test_command")
    def test_secret_command(self, command: CactusUtils.Command):
        self.utils.show_info("Секретная команда сработала!")
        return HookResult(strategy=HookStrategy.CANCEL)
    ```
