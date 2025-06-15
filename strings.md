
> Локализация строк происходит автоматически, вам больше не нужно создавать какие-либо отдельные классы для этого. Достаточно в классе плагина объявить переменную `strings` и в ней по локалям разделить строки.

```python
__id__ = "mytestplugin"

class MyPlugin(CactusUtils.Plugin):
    strings = {
        "en": {
            "app": "exteraGram",
            "hello": "Hello {}!",
            "pid": "Plugin id is {id}",
        },
        "ru": {
            "hello": "Привет {}!",
            "pid": "ID плагина: {id}",
        }
    }

    def testfunc(self):
        # CactusLib автоматически выберет язык системы
        # Если перевод для языка системы отсутствует, будет использован "en" по умолчанию

        # Форматирование через позиционные аргументы
        hello_string = self.string("hello", self.string("app"))
        # Результат (en): "Hello exteraGram!"
        # Результат (ru): "Привет exteraGram!" (ключ "app" взят из en, т.к. в ru его нет)

        # Форматирование через именованные аргументы
        my_name = self.string("pid", id=self.id)
        # Результат (en): "Plugin id is mytestplugin"
        # Результат (ru): "ID плагина: mytestplugin"
```